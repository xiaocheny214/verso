"""按事件类型分发给具体消费者，并用 framework 的客户端拉取；同时定期执行 Outbox 补发。"""

from __future__ import annotations

import logging
import time

from verso_app.worker.jobs.knowledge import consume_knowledge_process
from verso_app.worker.jobs.portrait import consume_portrait_sync
from verso_framework.db import get_session_factory
from verso_framework.mq import JobEventType, OutboxService, RocketMqConsumer, RocketMqProducer
from verso_framework.mq.event import DeliveryEvent

logger = logging.getLogger("verso.worker.jobs")

_RELAY_INTERVAL_SEC = 5.0


def handle_job(event: DeliveryEvent) -> None:
    if event.event_type == JobEventType.PORTRAIT_SYNC:
        consume_portrait_sync(event)
        return
    if event.event_type == JobEventType.KNOWLEDGE_DOCUMENT_PROCESS:
        consume_knowledge_process(event)
        return
    raise ValueError(f"未知作业 {event.event_type}")


def run_job_loop(
    consumer: RocketMqConsumer | None = None,
    producer: RocketMqProducer | None = None,
) -> None:
    mq = consumer or RocketMqConsumer()
    prod = producer or RocketMqProducer()
    factory = get_session_factory()
    last_relay = 0.0

    logger.info("job consumer started")
    while True:
        mq.poll(handle_job)

        # 定期进行 Outbox 补偿扫描
        now = time.monotonic()
        if now - last_relay >= _RELAY_INTERVAL_SEC:
            last_relay = now
            try:
                with factory() as session:
                    sent = OutboxService.relay_pending(session, producer=prod, limit=50)
                    if sent > 0:
                        logger.info("Outbox relay 补偿发送完成: %s 条", sent)
            except Exception:
                logger.exception("Outbox relay 补偿轮询异常")
