"""成色表。只有本模块改分；auth 只调用开户。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import Eligibility
from verso_framework.db.base import Base


class Reputation(Base):
    __tablename__ = "reputations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=REPUTATION_INITIAL_SCORE)
    eligibility: Mapped[str] = mapped_column(String(16), nullable=False, default=Eligibility.ACTIVE)
    suspended_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
