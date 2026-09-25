"""知识库 CRUD 与库内文档元数据。采集记录不属于知识库。"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from verso_app.server.collect.service import CollectService
from verso_app.server.knowledge.models import KnowledgeBase, KnowledgeDocument
from verso_common.enums import ArticleStatus, BizCode, DocumentStatus
from verso_common.exceptions import BizException
from verso_framework.config import get_app_settings

_COLLECTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_PROCESS_MODES = frozenset({"chunk", "none"})


class KnowledgeService:
    """当前用户拥有的知识库与文档。所有按 id 的查询都带 user_id。"""

    def create(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        name: str,
        collection_name: str | None = None,
        storage_profile_id: uuid.UUID | None = None,
    ) -> KnowledgeBase:
        clean_name = name.strip()
        if not clean_name:
            raise BizException("知识库名称不能为空", code=BizCode.BAD_REQUEST)
        if self._find_by_name(db, user_id=user_id, name=clean_name) is not None:
            raise BizException("知识库名称已存在", code=BizCode.CONFLICT)
        row_id = uuid.uuid4()
        row = KnowledgeBase(
            id=row_id,
            user_id=user_id,
            name=clean_name,
            embedding_model=get_app_settings().llm_embedding_model,
            collection_name=self._resolve_collection_name(
                db,
                user_id=user_id,
                name=clean_name,
                row_id=row_id,
                collection_name=collection_name,
            ),
            storage_profile_id=storage_profile_id,
        )
        db.add(row)
        db.flush()
        return row

    def list(self, db: Session, *, user_id: uuid.UUID) -> list[KnowledgeBase]:
        return list(
            db.scalars(
                select(KnowledgeBase)
                .where(KnowledgeBase.user_id == user_id)
                .order_by(KnowledgeBase.created_at.asc(), KnowledgeBase.id.asc())
            ).all()
        )

    def get(
        self, db: Session, *, user_id: uuid.UUID, knowledge_base_id: uuid.UUID
    ) -> KnowledgeBase:
        row = db.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        if row is None:
            raise BizException("知识库不存在", code=BizCode.NOT_FOUND)
        return row

    def update(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        name: str | None = None,
        collection_name: str | None = None,
        storage_profile_id: uuid.UUID | None = None,
        update_storage_profile: bool = False,
    ) -> KnowledgeBase:
        row = self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise BizException("知识库名称不能为空", code=BizCode.BAD_REQUEST)
            duplicate = self._find_by_name(db, user_id=user_id, name=clean_name, exclude_id=row.id)
            if duplicate is not None:
                raise BizException("知识库名称已存在", code=BizCode.CONFLICT)
            row.name = clean_name
        if collection_name is not None:
            row.collection_name = self._require_collection_name(
                db,
                user_id=user_id,
                collection_name=collection_name,
                exclude_id=row.id,
            )
        if update_storage_profile:
            row.storage_profile_id = storage_profile_id
        db.flush()
        return row

    def delete(self, db: Session, *, user_id: uuid.UUID, knowledge_base_id: uuid.UUID) -> None:
        row = self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        count = db.scalar(
            select(func.count())
            .select_from(KnowledgeDocument)
            .where(KnowledgeDocument.knowledge_base_id == row.id)
        )
        if count:
            raise BizException("知识库仍有文档，无法删除", code=BizCode.CONFLICT)
        db.delete(row)
        db.flush()

    def get_or_create_default(self, db: Session, *, user_id: uuid.UUID) -> KnowledgeBase:
        row = self._find_by_name(db, user_id=user_id, name="Default")
        if row is not None:
            return row
        return self.create(db, user_id=user_id, name="Default")

    def list_documents(
        self, db: Session, *, user_id: uuid.UUID, knowledge_base_id: uuid.UUID
    ) -> list[KnowledgeDocument]:
        self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        return list(
            db.scalars(
                select(KnowledgeDocument)
                .where(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
                .order_by(KnowledgeDocument.created_at.asc(), KnowledgeDocument.id.asc())
            ).all()
        )

    def get_document(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> KnowledgeDocument:
        self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        row = db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
            )
        )
        if row is None:
            raise BizException("文档不存在", code=BizCode.NOT_FOUND)
        return row

    def attach_from_collect(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        source_url: str,
        collect: CollectService,
    ) -> KnowledgeDocument:
        self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        clean_url = source_url.strip()
        if not clean_url:
            raise BizException("source_url 不能为空", code=BizCode.BAD_REQUEST)

        existing = self._find_document_by_source(
            db, knowledge_base_id=knowledge_base_id, source_url=clean_url
        )
        record = collect.get_by_source(db, user_id=user_id, source_url=clean_url)
        if record is None or record.status != ArticleStatus.READY:
            raise BizException("采集记录未就绪，无法挂接", code=BizCode.BAD_REQUEST)

        if existing is not None:
            if (
                existing.object_key == record.object_key
                and existing.content_hash == record.content_hash
            ):
                return existing
            existing.title = record.title
            existing.object_key = record.object_key
            existing.content_type = "markdown"
            existing.mime_type = "text/markdown"
            existing.byte_size = record.byte_size
            existing.content_hash = record.content_hash
            existing.source_type = "zhihu"
            existing.source_url = clean_url
            existing.status = DocumentStatus.PENDING
            existing.error_class = None
            existing.chunk_count = 0
            db.flush()
            return existing

        other = db.scalar(
            select(KnowledgeDocument).where(KnowledgeDocument.object_key == record.object_key)
        )
        if other is not None:
            raise BizException("对象键已被其他文档占用", code=BizCode.CONFLICT)

        row = KnowledgeDocument(
            knowledge_base_id=knowledge_base_id,
            title=record.title,
            enabled=True,
            chunk_count=0,
            object_key=record.object_key,
            content_type="markdown",
            mime_type="text/markdown",
            byte_size=record.byte_size,
            content_hash=record.content_hash,
            process_mode="chunk",
            chunk_strategy="paragraph_window",
            status=DocumentStatus.PENDING,
            source_type="zhihu",
            source_url=clean_url,
        )
        db.add(row)
        db.flush()
        return row

    def update_document(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        title: str | None = None,
        enabled: bool | None = None,
        process_mode: str | None = None,
        chunk_strategy: str | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
        clear_chunk_size: bool = False,
        clear_overlap: bool = False,
    ) -> KnowledgeDocument:
        row = self.get_document(
            db,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )
        if title is not None:
            row.title = title.strip()
        if enabled is not None:
            row.enabled = enabled
        if process_mode is not None:
            clean_mode = process_mode.strip()
            if clean_mode not in _PROCESS_MODES:
                raise BizException("process_mode 无效", code=BizCode.BAD_REQUEST)
            row.process_mode = clean_mode
        if chunk_strategy is not None:
            clean_strategy = chunk_strategy.strip()
            if not clean_strategy:
                raise BizException("chunk_strategy 不能为空", code=BizCode.BAD_REQUEST)
            row.chunk_strategy = clean_strategy
        if clear_chunk_size:
            row.chunk_size = None
        elif chunk_size is not None:
            if chunk_size < 1:
                raise BizException("chunk_size 无效", code=BizCode.BAD_REQUEST)
            row.chunk_size = chunk_size
        if clear_overlap:
            row.overlap = None
        elif overlap is not None:
            if overlap < 0:
                raise BizException("overlap 无效", code=BizCode.BAD_REQUEST)
            row.overlap = overlap
        db.flush()
        return row

    def delete_document(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> None:
        row = self.get_document(
            db,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )
        # 与 collect 可能共享 object_key：本切片只删元数据，不删对象字节。
        db.delete(row)
        db.flush()

    def _resolve_collection_name(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        name: str,
        row_id: uuid.UUID,
        collection_name: str | None,
    ) -> str:
        if collection_name is not None:
            return self._require_collection_name(
                db, user_id=user_id, collection_name=collection_name
            )
        candidate = _derived_collection_name(name, row_id)
        if self._find_by_collection_name(db, user_id=user_id, collection_name=candidate) is None:
            return candidate
        fallback = f"kb_{row_id.hex}"
        if self._find_by_collection_name(db, user_id=user_id, collection_name=fallback) is not None:
            raise BizException("collection_name 已存在", code=BizCode.CONFLICT)
        return fallback

    def _require_collection_name(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        collection_name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> str:
        clean = collection_name.strip().lower()
        if not _COLLECTION_NAME_RE.fullmatch(clean):
            raise BizException(
                "collection_name 只能包含小写字母、数字和下划线，并以字母开头",
                code=BizCode.BAD_REQUEST,
            )
        duplicate = self._find_by_collection_name(
            db, user_id=user_id, collection_name=clean, exclude_id=exclude_id
        )
        if duplicate is not None:
            raise BizException("collection_name 已存在", code=BizCode.CONFLICT)
        return clean

    @staticmethod
    def _find_by_name(
        db: Session,
        *,
        user_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBase.id != exclude_id)
        return db.scalar(stmt)

    @staticmethod
    def _find_by_collection_name(
        db: Session,
        *,
        user_id: uuid.UUID,
        collection_name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.collection_name == collection_name,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBase.id != exclude_id)
        return db.scalar(stmt)

    @staticmethod
    def _find_document_by_source(
        db: Session,
        *,
        knowledge_base_id: uuid.UUID,
        source_url: str,
    ) -> KnowledgeDocument | None:
        return db.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == knowledge_base_id,
                KnowledgeDocument.source_url == source_url,
            )
        )


def _derived_collection_name(name: str, row_id: uuid.UUID) -> str:
    if name == "Default":
        return "default"
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if _COLLECTION_NAME_RE.fullmatch(slug):
        return slug
    return f"kb_{row_id.hex}"
