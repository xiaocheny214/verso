"""消费 ``knowledge.document.process_requested``。

执行文档处理流水线：状态流转、分块、向量化、Milvus 写入。
通过 ``consumed_events`` 进行消费端幂等防重。
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.exc import IntegrityError

from verso_app.server.knowledge.service import KnowledgeService
from verso_common.exceptions import BizException
from verso_framework.db import get_session_factory
from verso_framework.mq.event import DeliveryEvent, KnowledgeProcessPayload
from verso_framework.mq.models import ConsumedEvent

logger = logging.getLogger("verso.worker.knowledge")


def consume_knowledge_process(event: DeliveryEvent) -> None:
    payload = event.payload
    if not isinstance(payload, KnowledgeProcessPayload):
        raise TypeError("payload 与文档处理不一致")

    factory = get_session_factory()
    with factory() as session:
        # 1. 消费端幂等检查与占位
        consumed = ConsumedEvent(
            event_id=event.event_id,
            event_type=event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type),
        )
        try:
            session.add(consumed)
            session.flush()
        except IntegrityError:
            # 主键冲突：已被消费过，安全幂等退出并确认
            session.rollback()
            logger.info("事件已消费过，跳过重复处理 (event_id=%s)", event.event_id)
            return

        # 2. 执行文档处理业务流
        try:
            KnowledgeService().execute_process_document(
                session,
                run_id=uuid.UUID(payload.run_id),
            )
            session.commit()
        except BizException as exc:
            # 业务类确定性错误（如文档已被删除、非法格式等）：execute_process_document 已置 run 为 FAILED
            # 此时仍提交事务保留 ConsumedEvent，以便正常 ACK 该消息，避免死循环重试
            session.commit()
            logger.warning("文档处理业务失败 (run_id=%s): %s", payload.run_id, exc)
        except Exception:
            # 意外错误（Milvus 断连、Embedder 网络超时等）：回滚，不记录 ConsumedEvent，向外抛出触发 RocketMQ 重试
            session.rollback()
            logger.exception("文档处理发生未预期异常，触发重试 (run_id=%s)", payload.run_id)
            raise
