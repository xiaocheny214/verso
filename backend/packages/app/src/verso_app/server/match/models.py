"""match_conditions：这次想学什么。擅长读 portraits，不拷进本表。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    TypeDecorator,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from verso_common.enums import MatchConditionStatus
from verso_framework.db.base import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


class MatchCondition(Base):
    __tablename__ = "match_conditions"
    __table_args__ = (
        Index(
            "match_conditions_one_waiting_per_user",
            "user_id",
            unique=True,
            sqlite_where=text("status = 'waiting'"),
            postgresql_where=text("status = 'waiting'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    want_text: Mapped[str] = mapped_column(Text, nullable=False)
    want_tag: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=MatchConditionStatus.WAITING
    )
    pair_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    waiting_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pair_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class UuidList(TypeDecorator):
    """两个条件 id。Postgres 用 uuid[]，SQLite 测试用 JSON 字符串。"""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(Uuid(as_uuid=True)))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]
        return [str(item) for item in value]

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return [item if isinstance(item, uuid.UUID) else uuid.UUID(str(item)) for item in value]


class MatchEvaluation(Base):
    """一次模型参与的双向判断。condition_ids 不分先后，人与问题回匹配表查。"""

    __tablename__ = "match_evaluations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    condition_ids: Mapped[list[uuid.UUID]] = mapped_column(UuidList(), nullable=False)
    sides: Mapped[dict] = mapped_column(JSONType, nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_class: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    label_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    labeled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
