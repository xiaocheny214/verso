"""当前用户知识库与库内文档。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.knowledge.models import KnowledgeBase, KnowledgeDocument
from verso_app.server.knowledge.service import KnowledgeService
from verso_app.web.api.collect import (
    BrowserCaptureBody,
    CollectDep,
    StoreDep,
    _failed_list,
    _queue_view,
    _view,
)
from verso_app.web.middleware.auth import SessionDep, get_current_user
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_common.models import (
    ArchiveQueueView,
    ArticleArchiveView,
    FailedFetchListView,
    KnowledgeBaseView,
    KnowledgeDocumentView,
)
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["knowledge"])

KnowledgeDep = Annotated[KnowledgeService, Depends(KnowledgeService)]
UserDep = Annotated[User, Depends(get_current_user)]


class KnowledgeBaseCreateBody(BaseModel):
    name: str = Field(min_length=1)
    collection_name: str | None = Field(default=None, max_length=128)
    storage_profile_id: uuid.UUID | None = None


class KnowledgeBasePatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    collection_name: str | None = Field(default=None, max_length=128)
    storage_profile_id: uuid.UUID | None = None


class FromCollectBody(BaseModel):
    source_url: str = Field(min_length=1)


class KnowledgeDocumentPatchBody(BaseModel):
    title: str | None = None
    enabled: bool | None = None
    process_mode: str | None = None
    chunk_strategy: str | None = None
    chunk_size: int | None = None
    overlap: int | None = None


def _base_view(row: KnowledgeBase) -> KnowledgeBaseView:
    return KnowledgeBaseView(
        id=str(row.id),
        name=row.name,
        embedding_model=row.embedding_model,
        collection_name=row.collection_name,
        storage_profile_id=str(row.storage_profile_id) if row.storage_profile_id else None,
    )


def _document_view(row: KnowledgeDocument) -> KnowledgeDocumentView:
    return KnowledgeDocumentView(
        id=str(row.id),
        knowledge_base_id=str(row.knowledge_base_id),
        title=row.title,
        enabled=row.enabled,
        chunk_count=row.chunk_count,
        object_key=row.object_key,
        content_type=row.content_type,
        mime_type=row.mime_type,
        byte_size=row.byte_size,
        content_hash=row.content_hash,
        process_mode=row.process_mode,
        chunk_strategy=row.chunk_strategy,
        chunk_size=row.chunk_size,
        overlap=row.overlap,
        status=row.status,
        error_class=row.error_class,
        source_type=row.source_type,
        source_url=row.source_url,
    )


@router.get("/me/knowledge-bases")
def list_knowledge_bases(
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[list[KnowledgeBaseView]]:
    return ApiResponse.success(
        [_base_view(row) for row in knowledge.list(session, user_id=user.id)]
    )


@router.post("/me/knowledge-bases")
def create_knowledge_base(
    body: KnowledgeBaseCreateBody,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[KnowledgeBaseView]:
    row = knowledge.create(
        session,
        user_id=user.id,
        name=body.name,
        collection_name=body.collection_name,
        storage_profile_id=body.storage_profile_id,
    )
    return ApiResponse.success(_base_view(row))


@router.get("/me/knowledge-bases/{knowledge_base_id}")
def get_knowledge_base(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[KnowledgeBaseView]:
    return ApiResponse.success(
        _base_view(knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id))
    )


@router.patch("/me/knowledge-bases/{knowledge_base_id}")
def patch_knowledge_base(
    knowledge_base_id: uuid.UUID,
    body: KnowledgeBasePatchBody,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[KnowledgeBaseView]:
    row = knowledge.update(
        session,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        name=body.name,
        collection_name=body.collection_name,
        storage_profile_id=body.storage_profile_id,
        update_storage_profile="storage_profile_id" in body.model_fields_set,
    )
    return ApiResponse.success(_base_view(row))


@router.delete("/me/knowledge-bases/{knowledge_base_id}")
def delete_knowledge_base(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[None]:
    knowledge.delete(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success()


@router.get("/me/knowledge-bases/{knowledge_base_id}/documents")
def list_knowledge_documents(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[list[KnowledgeDocumentView]]:
    rows = knowledge.list_documents(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success([_document_view(row) for row in rows])


@router.post("/me/knowledge-bases/{knowledge_base_id}/documents/from-collect")
def attach_knowledge_document_from_collect(
    knowledge_base_id: uuid.UUID,
    body: FromCollectBody,
    session: SessionDep,
    knowledge: KnowledgeDep,
    collect: CollectDep,
    user: UserDep,
) -> ApiResponse[KnowledgeDocumentView]:
    row = knowledge.attach_from_collect(
        session,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        source_url=body.source_url,
        collect=collect,
    )
    return ApiResponse.success(_document_view(row))


@router.get("/me/knowledge-bases/{knowledge_base_id}/documents/{document_id}")
def get_knowledge_document(
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[KnowledgeDocumentView]:
    row = knowledge.get_document(
        session,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )
    return ApiResponse.success(_document_view(row))


@router.patch("/me/knowledge-bases/{knowledge_base_id}/documents/{document_id}")
def patch_knowledge_document(
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    body: KnowledgeDocumentPatchBody,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[KnowledgeDocumentView]:
    fields = body.model_fields_set
    row = knowledge.update_document(
        session,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
        title=body.title if "title" in fields else None,
        enabled=body.enabled if "enabled" in fields else None,
        process_mode=body.process_mode if "process_mode" in fields else None,
        chunk_strategy=body.chunk_strategy if "chunk_strategy" in fields else None,
        chunk_size=body.chunk_size if "chunk_size" in fields else None,
        overlap=body.overlap if "overlap" in fields else None,
        clear_chunk_size="chunk_size" in fields and body.chunk_size is None,
        clear_overlap="overlap" in fields and body.overlap is None,
    )
    return ApiResponse.success(_document_view(row))


@router.delete("/me/knowledge-bases/{knowledge_base_id}/documents/{document_id}")
def delete_knowledge_document(
    knowledge_base_id: uuid.UUID,
    document_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[None]:
    knowledge.delete_document(
        session,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        document_id=document_id,
    )
    return ApiResponse.success()


@router.get("/me/knowledge-bases/{knowledge_base_id}/articles")
def list_knowledge_base_articles(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    user: UserDep,
) -> ApiResponse[list[KnowledgeDocumentView]]:
    """兼容旧路径：按库列出文档元数据（不再扁平返回 collect）。"""
    rows = knowledge.list_documents(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success([_document_view(row) for row in rows])


@router.get("/me/knowledge-bases/{knowledge_base_id}/articles/queue")
def list_knowledge_base_queue(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    collect: CollectDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[ArchiveQueueView]:
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success(_queue_view(session, collect, store, user))


@router.get("/me/knowledge-bases/{knowledge_base_id}/articles/failed-fetch")
def list_knowledge_base_failed_fetch(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    collect: CollectDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[FailedFetchListView]:
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success(_failed_list(session, collect, store, user))


@router.post("/me/knowledge-bases/{knowledge_base_id}/articles/browser-capture")
def capture_knowledge_base_article(
    knowledge_base_id: uuid.UUID,
    body: BrowserCaptureBody,
    session: SessionDep,
    knowledge: KnowledgeDep,
    collect: CollectDep,
    store: StoreDep,
) -> ApiResponse[ArticleArchiveView]:
    user_id = store.user_id_for_capture(body.token)
    if not user_id:
        raise BizException("补抓凭证无效或已过期", code=BizCode.UNAUTHORIZED)
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise BizException("补抓凭证无效或已过期", code=BizCode.UNAUTHORIZED)
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    row = collect.capture_from_browser(
        session,
        user_id=user.id,
        source_url=body.source_url,
        html=body.html,
        title=body.title,
    )
    return ApiResponse.success(_view(row))
