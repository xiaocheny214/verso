"""match_conditions：这次想学什么。擅长读 portraits，不拷进本表。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from verso_common.enums import MatchConditionStatus
from verso_framework.db.base import Base


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
