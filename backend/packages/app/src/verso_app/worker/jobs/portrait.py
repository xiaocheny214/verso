"""消费 ``portrait.sync_requested``。授权过期不再重投，其余失败留给 Broker 重试。"""

from __future__ import annotations

import logging

from verso_app.worker.handlers import sync_portrait
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_framework.mq.event import DeliveryEvent, PortraitSyncPayload

logger = logging.getLogger("verso.worker.portrait")


def consume_portrait_sync(event: DeliveryEvent) -> None:
    payload = event.payload
    if not isinstance(payload, PortraitSyncPayload):
        raise TypeError("payload 与画像同步不一致")
    try:
        sync_portrait(payload.user_id)
    except BizException as exc:
        if exc.code == BizCode.UNAUTHORIZED:
            logger.info(
                "画像同步跳过：授权过期 user_id=%s event_id=%s", payload.user_id, event.event_id
            )
            return
        raise
