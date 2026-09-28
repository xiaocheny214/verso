"""intent_nodes 意图节点模型。

以扁平父子关系存储，按 user_id 租户隔离。
parent_id 为空表示根节点；非空表示父节点。
kind 当前仅支持 kb_retrieve。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from verso_common.enums import IntentKind, IntentLayer
from verso_framework.db.base import Base


class IntentNode(Base):
    __tablename__ = "intent_nodes"
    __table_args__ = (
        UniqueConstraint("user_id", "identifier", name="intent_nodes_user_identifier"),
        Index("idx_intent_nodes_user_id", "user_id"),
        Index("idx_intent_nodes_parent_id", "parent_id"),
        Index("idx_intent_nodes_kb_id", "knowledge_base_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("intent_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    identifier: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    layer: Mapped[str] = mapped_column(String(16), nullable=False, default=IntentLayer.OTHER)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default=IntentKind.KB_RETRIEVE)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    examples: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    topic_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
