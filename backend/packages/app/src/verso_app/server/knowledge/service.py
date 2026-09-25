"""知识库 CRUD、库内文档元数据与 process 编排。采集记录不属于知识库。"""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from verso_app.server.chunk import (
    ChunkService,
    ChunkSplitResult,
    normalize_chunk_strategy,
    parse_chunk_strategy_params,
)
from verso_app.server.collect.service import CollectService
from verso_app.server.knowledge.models import (
    DocumentProcessRun,
    KnowledgeBase,
    KnowledgeDocument,
)
from verso_app.server.knowledge.vector_store import (
    ChunkVectorPoint,
    ChunkVectorStore,
    MilvusChunkVectorStore,
)
from verso_common.enums import (
    ArticleStatus,
    BizCode,
    ChunkStrategy,
    DocumentStatus,
    ProcessRunStatus,
)
from verso_common.exceptions import BizException
from verso_framework.config import get_app_settings
from verso_framework.embed import Embedder, build_embedder
from verso_framework.storage import ObjectStore, ObjectStoreError, get_object_store

_COLLECTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_PROCESS_MODES = frozenset({"chunk", "none"})
_ERROR_MESSAGE_MAX = 2000


class KnowledgeService:
    """当前用户拥有的知识库与文档。所有按 id 的查询都带 user_id。"""

    def __init__(self) -> None:
        self._store: ObjectStore | None = None
        self._chunker = ChunkService()
        self._embedder: Embedder | None = None
        self._vectors: ChunkVectorStore | None = None

    @classmethod
    def with_deps(
        cls,
        store: ObjectStore | None = None,
        *,
        chunker: ChunkService | None = None,
        embedder: Embedder | None = None,
        vectors: ChunkVectorStore | None = None,
    ) -> KnowledgeService:
        service = cls()
        service._store = store
        if chunker is not None:
            service._chunker = chunker
        service._embedder = embedder
        service._vectors = vectors
        return service

    def _object_store(self) -> ObjectStore:
        if self._store is None:
            self._store = get_object_store()
        return self._store

    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            try:
                self._embedder = build_embedder(get_app_settings())
            except ValueError as exc:
                raise BizException(str(exc), code=BizCode.BAD_REQUEST) from exc
        return self._embedder

    def _vector_store(self) -> ChunkVectorStore:
        if self._vectors is None:
            self._vectors = MilvusChunkVectorStore()
        return self._vectors

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
        self._normalize_legacy_strategy(db, row)
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
            # 正文变更：回 pending，并清掉旧向量，避免 retrieve 命中过期块。
            self._vector_store().delete_document(user_id=user_id, document_id=existing.id)
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
            chunk_strategy=ChunkStrategy.FIXED_SIZE,
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
            row.chunk_strategy = normalize_chunk_strategy(chunk_strategy)
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

    def preview_chunks(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
        chunk_strategy: str | None = None,
        chunk_size: int | None = None,
        overlap: int | None = None,
    ) -> tuple[KnowledgeDocument, ChunkSplitResult]:
        row = self.get_document(
            db,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )
        self._normalize_legacy_strategy(db, row)

        params = parse_chunk_strategy_params(
            strategy=chunk_strategy or row.chunk_strategy,
            chunk_size=chunk_size if chunk_size is not None else row.chunk_size,
            overlap=overlap if overlap is not None else row.overlap,
        )
        if row.process_mode == "none":
            return row, self._chunker.split("", params)

        text = self._load_document_text(row)
        return row, self._chunker.split(text, params)

    def process_document(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> tuple[KnowledgeDocument, DocumentProcessRun]:
        row = self.get_document(
            db,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )
        self._normalize_legacy_strategy(db, row)

        started = datetime.now(UTC)
        started_mono = time.perf_counter()
        run = DocumentProcessRun(
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=row.id,
            status=ProcessRunStatus.RUNNING,
            process_mode=row.process_mode,
            chunk_strategy=row.chunk_strategy,
            chunk_size=row.chunk_size,
            overlap=row.overlap,
            started_at=started,
        )
        db.add(run)
        db.flush()

        try:
            chunk_count = self._run_process_pipeline(db, user_id=user_id, row=row)
        except BizException as exc:
            self._fail_process(db, row=row, run=run, started_mono=started_mono, exc=exc)
            raise
        except Exception as exc:
            self._fail_process(db, row=row, run=run, started_mono=started_mono, exc=exc)
            raise BizException("文档处理失败", code=BizCode.INTERNAL_ERROR) from exc

        finished = datetime.now(UTC)
        run.status = ProcessRunStatus.SUCCESS
        run.chunk_count = chunk_count
        run.error_class = None
        run.error_message = None
        run.total_duration_ms = int((time.perf_counter() - started_mono) * 1000)
        run.finished_at = finished
        row.status = DocumentStatus.SUCCESS
        row.chunk_count = chunk_count
        row.error_class = None
        db.flush()
        return row, run

    def list_process_runs(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[DocumentProcessRun]:
        self.get_document(
            db,
            user_id=user_id,
            knowledge_base_id=knowledge_base_id,
            document_id=document_id,
        )
        return list(
            db.scalars(
                select(DocumentProcessRun)
                .where(DocumentProcessRun.document_id == document_id)
                .order_by(
                    DocumentProcessRun.started_at.desc().nullslast(),
                    DocumentProcessRun.created_at.desc(),
                    DocumentProcessRun.id.desc(),
                )
            ).all()
        )

    def _run_process_pipeline(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        row: KnowledgeDocument,
    ) -> int:
        vectors = self._vector_store()

        if row.process_mode == "none":
            vectors.delete_document(user_id=user_id, document_id=row.id)
            return 0

        params = parse_chunk_strategy_params(
            strategy=row.chunk_strategy,
            chunk_size=row.chunk_size,
            overlap=row.overlap,
        )
        text = self._load_document_text(row)
        split = self._chunker.split(text, params)
        if not split.chunks:
            vectors.delete_document(user_id=user_id, document_id=row.id)
            return 0

        embedder = self._get_embedder()
        embeddings = embedder.embed_documents([chunk.text for chunk in split.chunks])
        if len(embeddings) != len(split.chunks):
            raise BizException("embedding 数量与切块不一致", code=BizCode.INTERNAL_ERROR)

        dimension = embedder.dimensions if embedder.dimensions is not None else len(embeddings[0])
        if dimension < 1:
            raise BizException("embedding 维度无效", code=BizCode.INTERNAL_ERROR)

        snapshot = {
            "title": row.title,
            "source_type": row.source_type,
            "source_url": row.source_url or "",
        }
        points = [
            ChunkVectorPoint(
                user_id=user_id,
                knowledge_base_id=row.knowledge_base_id,
                document_id=row.id,
                chunk_index=chunk.index,
                char_start=chunk.char_start,
                char_end=chunk.char_end,
                embedding=embeddings[index],
                metadata=snapshot,
            )
            for index, chunk in enumerate(split.chunks)
        ]
        vectors.ensure_collection(dimension=dimension)
        vectors.delete_document(user_id=user_id, document_id=row.id)
        vectors.upsert(points)
        return len(points)

    def _fail_process(
        self,
        db: Session,
        *,
        row: KnowledgeDocument,
        run: DocumentProcessRun,
        started_mono: float,
        exc: BaseException,
    ) -> None:
        message = str(exc).strip() or type(exc).__name__
        if len(message) > _ERROR_MESSAGE_MAX:
            message = message[:_ERROR_MESSAGE_MAX]
        run.status = ProcessRunStatus.FAILED
        run.error_class = type(exc).__name__
        run.error_message = message
        run.total_duration_ms = int((time.perf_counter() - started_mono) * 1000)
        run.finished_at = datetime.now(UTC)
        row.status = DocumentStatus.FAILED
        row.error_class = run.error_class
        db.flush()

    def _normalize_legacy_strategy(self, db: Session, row: KnowledgeDocument) -> None:
        if row.chunk_strategy == "paragraph_window":
            row.chunk_strategy = ChunkStrategy.FIXED_SIZE
            db.flush()

    def _load_document_text(self, row: KnowledgeDocument) -> str:
        try:
            data = self._object_store().get(row.object_key)
        except (KeyError, ObjectStoreError) as exc:
            raise BizException("文档正文不存在", code=BizCode.NOT_FOUND) from exc
        return data.decode("utf-8")

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
        # 先清 Milvus，再删 PG（process_runs 随 document FK CASCADE）。
        # 不删对象存储：object_key 常与 collect 共享；正文生命周期归 collect。
        # 无 knowledge_chunks 表：块定位只在 Milvus（chunk_index + char_*）。
        try:
            self._vector_store().delete_document(user_id=user_id, document_id=row.id)
        except Exception as exc:
            raise BizException(
                "文档向量清理失败，未删除文档元数据",
                code=BizCode.INTERNAL_ERROR,
            ) from exc
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
