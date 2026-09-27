"""本地消息表与消费幂等表 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from verso_framework.db.base import Base

_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class OutboxMessage(Base):
    """本地消息表：与业务写在同一数据库事务中，用于可靠投递。"""

    __tablename__ = "outbox_messages"
    __table_args__ = (
        Index("idx_outbox_status_created", "status", "created_at"),
        Index("idx_outbox_event_type", "event_type"),
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    producer: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsumedEvent(Base):
    """消费者幂等表：记录已消费的消息 ID，防止重复执行。"""

    __tablename__ = "consumed_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    consumed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
