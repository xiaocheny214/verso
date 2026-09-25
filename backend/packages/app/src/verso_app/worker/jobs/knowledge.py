"""消费 ``knowledge.document.process_requested``。

失败不确认消息。当前 ``process_document`` 每次调用都会新建一次 run，
``payload.run_id`` 要等文档处理改成受理已有 run 后再用。
"""

from __future__ import annotations

import uuid

from verso_app.server.knowledge.service import KnowledgeService
from verso_framework.db import get_session_factory
from verso_framework.mq.event import DeliveryEvent, KnowledgeProcessPayload


def consume_knowledge_process(event: DeliveryEvent) -> None:
    payload = event.payload
    if not isinstance(payload, KnowledgeProcessPayload):
        raise TypeError("payload 与文档处理不一致")
    factory = get_session_factory()
    with factory() as session:
        try:
            KnowledgeService().process_document(
                session,
                user_id=uuid.UUID(payload.user_id),
                knowledge_base_id=uuid.UUID(payload.knowledge_base_id),
                document_id=uuid.UUID(payload.document_id),
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
