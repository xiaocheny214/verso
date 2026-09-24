"""当前用户知识库与按库访问文章。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.knowledge.models import KnowledgeBase
from verso_app.server.knowledge.service import KnowledgeService
from verso_app.web.api.article import (
    ArchiveDep,
    BrowserCaptureBody,
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
)
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["knowledge"])

KnowledgeDep = Annotated[KnowledgeService, Depends(KnowledgeService)]
UserDep = Annotated[User, Depends(get_current_user)]


class KnowledgeBaseCreateBody(BaseModel):
    name: str = Field(min_length=1)
    storage_profile_id: uuid.UUID | None = None


class KnowledgeBasePatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    storage_profile_id: uuid.UUID | None = None


def _base_view(row: KnowledgeBase) -> KnowledgeBaseView:
    return KnowledgeBaseView(
        id=str(row.id),
        name=row.name,
        embedding_model=row.embedding_model,
        collection=row.collection,
        storage_profile_id=str(row.storage_profile_id) if row.storage_profile_id else None,
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


@router.get("/me/knowledge-bases/{knowledge_base_id}/articles")
def list_knowledge_base_articles(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    archive: ArchiveDep,
    user: UserDep,
) -> ApiResponse[list[ArticleArchiveView]]:
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    rows = archive.list_by_knowledge_base(
        session, user_id=user.id, knowledge_base_id=knowledge_base_id
    )
    return ApiResponse.success([_view(row) for row in rows])


@router.get("/me/knowledge-bases/{knowledge_base_id}/articles/queue")
def list_knowledge_base_queue(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    archive: ArchiveDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[ArchiveQueueView]:
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success(
        _queue_view(
            session,
            archive,
            store,
            user,
            knowledge_base_id=knowledge_base_id,
        )
    )


@router.get("/me/knowledge-bases/{knowledge_base_id}/articles/failed-fetch")
def list_knowledge_base_failed_fetch(
    knowledge_base_id: uuid.UUID,
    session: SessionDep,
    knowledge: KnowledgeDep,
    archive: ArchiveDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[FailedFetchListView]:
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    return ApiResponse.success(
        _failed_list(
            session,
            archive,
            store,
            user,
            knowledge_base_id=knowledge_base_id,
        )
    )


@router.post("/me/knowledge-bases/{knowledge_base_id}/articles/browser-capture")
def capture_knowledge_base_article(
    knowledge_base_id: uuid.UUID,
    body: BrowserCaptureBody,
    session: SessionDep,
    knowledge: KnowledgeDep,
    archive: ArchiveDep,
    store: StoreDep,
) -> ApiResponse[ArticleArchiveView]:
    user_id = store.user_id_for_capture(body.token)
    if not user_id:
        raise BizException("补抓凭证无效或已过期", code=BizCode.UNAUTHORIZED)
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise BizException("补抓凭证无效或已过期", code=BizCode.UNAUTHORIZED)
    knowledge.get(session, user_id=user.id, knowledge_base_id=knowledge_base_id)
    row = archive.capture_from_browser(
        session,
        user_id=user.id,
        knowledge_base_id=knowledge_base_id,
        source_url=body.source_url,
        html=body.html,
        title=body.title,
    )
    return ApiResponse.success(_view(row))
