"""本地消息表与 Outbox 投递/重试服务。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_framework.mq.models import OutboxMessage

if TYPE_CHECKING:
    from verso_framework.mq.event import DeliveryEvent
    from verso_framework.mq.producer import RocketMqProducer

logger = logging.getLogger("verso.framework.mq.outbox")


class OutboxService:
    @staticmethod
    def save_event(db: Session, event: DeliveryEvent) -> OutboxMessage:
        """在当前事务中保存一条 pending outbox 消息。"""
        row = OutboxMessage(
            event_id=event.event_id,
            event_type=event.event_type.value
            if hasattr(event.event_type, "value")
            else str(event.event_type),
            schema_version=event.schema_version,
            producer=event.producer,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload.model_dump()
            if hasattr(event.payload, "model_dump")
            else dict(event.payload),
            status="pending",
            retry_count=0,
            created_at=event.occurred_at or datetime.now(UTC),
        )
        db.add(row)
        db.flush()
        return row

    @staticmethod
    def mark_published(db: Session, event_id: str) -> None:
        """标记消息已成功发送至 Broker。"""
        row = db.get(OutboxMessage, event_id)
        if row is not None:
            row.status = "published"
            row.published_at = datetime.now(UTC)
            row.last_error = None
            db.flush()

    @staticmethod
    def mark_failed(db: Session, event_id: str, error: str) -> None:
        """记录发送失败原因并增加重试次数。"""
        row = db.get(OutboxMessage, event_id)
        if row is not None:
            row.retry_count += 1
            row.last_error = error[:2000]
            db.flush()

    @classmethod
    def publish_event(
        cls,
        db: Session,
        *,
        producer: RocketMqProducer,
        event: DeliveryEvent,
    ) -> bool:
        """事务提交后的直发快速通道。成功标 published；异常保持 pending 等待后台 relay。"""
        try:
            producer.publish(event)
            cls.mark_published(db, event.event_id)
            db.commit()
            return True
        except Exception as exc:
            logger.warning("直发 RocketMQ 失败 (event_id=%s): %s", event.event_id, exc)
            try:
                cls.mark_failed(db, event.event_id, str(exc))
                db.commit()
            except Exception:
                db.rollback()
            return False

    @classmethod
    def relay_pending(
        cls,
        db: Session,
        *,
        producer: RocketMqProducer,
        limit: int = 50,
    ) -> int:
        """后台轮询补发：读取待发送的 outbox 消息并投递。"""
        from verso_framework.mq.event import DeliveryEvent, JobEventType

        rows = list(
            db.scalars(
                select(OutboxMessage)
                .where(OutboxMessage.status == "pending")
                .order_by(OutboxMessage.created_at.asc())
                .limit(limit)
            ).all()
        )
        if not rows:
            return 0

        sent_count = 0
        for row in rows:
            try:
                event = DeliveryEvent(
                    event_id=row.event_id,
                    event_type=JobEventType(row.event_type),
                    schema_version=row.schema_version,
                    occurred_at=row.created_at,
                    producer=row.producer,
                    aggregate_type=row.aggregate_type,
                    aggregate_id=row.aggregate_id,
                    payload=row.payload,  # model_validator will parse into proper payload model
                )
                producer.publish(event)
                row.status = "published"
                row.published_at = datetime.now(UTC)
                row.last_error = None
                sent_count += 1
            except Exception as exc:
                logger.warning("Relay 补发消息失败 (event_id=%s): %s", row.event_id, exc)
                row.retry_count += 1
                row.last_error = str(exc)[:2000]

        db.commit()
        return sent_count
