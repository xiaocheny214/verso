"""按事件类型分发给具体消费者，并用 framework 的客户端拉取。"""

from __future__ import annotations

import logging

from verso_app.worker.jobs.knowledge import consume_knowledge_process
from verso_app.worker.jobs.portrait import consume_portrait_sync
from verso_framework.mq import JobEventType, RocketMqConsumer
from verso_framework.mq.event import DeliveryEvent

logger = logging.getLogger("verso.worker.jobs")


def handle_job(event: DeliveryEvent) -> None:
    if event.event_type == JobEventType.PORTRAIT_SYNC:
        consume_portrait_sync(event)
        return
    if event.event_type == JobEventType.KNOWLEDGE_DOCUMENT_PROCESS:
        consume_knowledge_process(event)
        return
    raise ValueError(f"未知作业 {event.event_type}")


def run_job_loop(consumer: RocketMqConsumer | None = None) -> None:
    mq = consumer or RocketMqConsumer()
    logger.info("job consumer started")
    while True:
        mq.poll(handle_job)
