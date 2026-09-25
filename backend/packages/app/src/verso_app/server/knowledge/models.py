"""knowledge_bases / knowledge_documents / document_process_runs。

正文在对象存储；本模块不落文章/分块明文。向量与定位在 Milvus。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from verso_common.enums import ChunkStrategy, DocumentStatus, ProcessRunStatus
from verso_framework.db.base import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="knowledge_bases_user_name"),
        UniqueConstraint("user_id", "collection", name="knowledge_bases_user_collection"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    collection_name: Mapped[str] = mapped_column(
        "collection", String(128), nullable=False, default="default"
    )
    storage_profile_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("idx_knowledge_documents_kb_id", "knowledge_base_id"),
        Index("idx_knowledge_documents_kb_status", "knowledge_base_id", "status"),
        Index(
            "knowledge_documents_kb_source_url",
            "knowledge_base_id",
            "source_url",
            unique=True,
            sqlite_where=text("source_url IS NOT NULL"),
            postgresql_where=text("source_url IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_bases.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    object_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    process_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="chunk")
    chunk_strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default=ChunkStrategy.FIXED_SIZE
    )
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DocumentStatus.PENDING)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class DocumentProcessRun(Base):
    """一次文档 process 运行记录；不含块正文。"""

    __tablename__ = "document_process_runs"
    __table_args__ = (
        Index("idx_document_process_runs_document_id", "document_id"),
        Index("idx_document_process_runs_kb_id", "knowledge_base_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_bases.id"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ProcessRunStatus.PENDING
    )
    process_mode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    chunk_strategy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chunk_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overlap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_class: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
