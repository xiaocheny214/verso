"""画像异步同步：消费 Redis 队列，并周期性扫过期用户入队。"""

from __future__ import annotations

import logging
import threading
import time
import uuid

from verso_app.server.auth.session_store import SessionStore
from verso_app.server.portrait.extractor import build_evidence_classifier
from verso_app.server.portrait.queue import PortraitSyncQueue
from verso_app.server.portrait.service import PortraitService
from verso_common.constants import PORTRAIT_SYNC_SCAN_INTERVAL_SEC
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_framework.config import get_app_settings
from verso_framework.db import get_redis, get_session_factory
from verso_framework.providers.zhihu import HttpxUserDataClient

logger = logging.getLogger("verso.worker.portrait")

_poller_started = False
_poller_lock = threading.Lock()


def sync_portrait(user_id: str) -> None:
    """执行一次画像同步。失败抛出，由调用方决定是否确认消息。"""
    settings = get_app_settings()
    factory = get_session_factory()
    store = SessionStore(get_redis())
    with factory() as session:
        try:
            PortraitService(
                session=session,
                grants=store,
                zhihu=HttpxUserDataClient(settings),
                classifier=build_evidence_classifier(settings),
            ).sync(uuid.UUID(user_id))
            session.commit()
        except Exception:
            session.rollback()
            raise


def process_portrait_sync(user_id: str) -> None:
    try:
        sync_portrait(user_id)
    except BizException as exc:
        if exc.code == BizCode.UNAUTHORIZED:
            logger.info("画像同步跳过：授权过期 user_id=%s", user_id)
        else:
            logger.warning("画像同步业务失败 user_id=%s code=%s", user_id, exc.code)
    except Exception:
        logger.exception("画像同步失败 user_id=%s", user_id)


def enqueue_stale_portraits(queue: PortraitSyncQueue) -> int:
    settings = get_app_settings()
    factory = get_session_factory()
    with factory() as session:
        service = PortraitService(
            session=session,
            grants=SessionStore(get_redis()),
            zhihu=HttpxUserDataClient(settings),
            queue=queue,
        )
        user_ids = service.list_stale_user_ids()
    enqueued = 0
    for user_id in user_ids:
        if queue.enqueue(str(user_id)):
            enqueued += 1
    if enqueued:
        logger.info("画像过期扫描入队 count=%s", enqueued)
    return enqueued


def run_portrait_sync_loop(
    *, once: bool = False, stop_event: threading.Event | None = None
) -> None:
    queue = PortraitSyncQueue(get_redis())
    last_scan = 0.0
    while True:
        if stop_event is not None and stop_event.is_set():
            return
        user_id = queue.pop(timeout_sec=5)
        if user_id:
            try:
                process_portrait_sync(user_id)
            finally:
                queue.ack(user_id)
        now = time.monotonic()
        if now - last_scan >= PORTRAIT_SYNC_SCAN_INTERVAL_SEC:
            try:
                enqueue_stale_portraits(queue)
            except Exception:
                logger.exception("画像过期扫描失败")
            last_scan = now
        if once:
            return


def schedule_portrait_sync_poller() -> None:
    """API 进程内轻量 poller，避免本地只起 API 时画像永远不跑。"""
    global _poller_started
    settings = get_app_settings()
    if not settings.portrait_sync_inline:
        return
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
    threading.Thread(
        target=run_portrait_sync_loop,
        daemon=True,
        name="portrait-sync-poller",
    ).start()
    logger.info("portrait sync inline poller started")
