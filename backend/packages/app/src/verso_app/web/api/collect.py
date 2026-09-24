"""当前用户的知乎采集记录。首次打开采集页拉列表，正文由用户回传后写入对象存储。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.auth.session_store import SessionStore
from verso_app.server.collect.models import ArticleCollectionRecord
from verso_app.server.collect.service import CollectService
from verso_app.web.middleware.auth import (
    SessionDep,
    get_collect_service,
    get_current_user,
    get_session_store,
)
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_common.models import ArchiveQueueView, ArticleArchiveView, FailedFetchListView
from verso_common.result import Response as ApiResponse
from verso_framework.config import get_app_settings
from verso_framework.providers.zhihu import HttpxUserDataClient

router = APIRouter(tags=["collect"])

CollectDep = Annotated[CollectService, Depends(get_collect_service)]
UserDep = Annotated[User, Depends(get_current_user)]
StoreDep = Annotated[SessionStore, Depends(get_session_store)]


class BrowserCaptureBody(BaseModel):
    token: str = Field(min_length=8)
    source_url: str = Field(min_length=8)
    html: str = Field(min_length=1)
    title: str = ""


def _view(row: ArticleCollectionRecord) -> ArticleArchiveView:
    return ArticleArchiveView(
        id=str(row.id),
        title=row.title,
        source_url=row.source_url,
        status=row.status,
        error_class=row.error_class,
    )


def _failed_list(
    session: Session,
    archive: CollectService,
    store: SessionStore,
    user: User,
) -> FailedFetchListView:
    items = [_view(row) for row in archive.list_failed_fetch(session, user_id=user.id)]
    token = store.put_capture_token(str(user.id)) if items else ""
    return FailedFetchListView(items=items, capture_token=token)


def _queue_view(
    session: Session,
    archive: CollectService,
    store: SessionStore,
    user: User,
) -> ArchiveQueueView:
    items = [_view(row) for row in archive.list_queue(session, user_id=user.id)]
    pending_count, failed_count, ready_count = archive.queue_counts(session, user_id=user.id)
    token = store.put_capture_token(str(user.id)) if items else ""
    return ArchiveQueueView(
        items=items,
        capture_token=token,
        pending_count=pending_count,
        failed_count=failed_count,
        ready_count=ready_count,
    )


@router.post("/me/articles/discover")
def discover_collection_records(
    session: SessionDep,
    archive: CollectDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[ArchiveQueueView]:
    """采集页首次进入时向知乎拉待采集列表。已有记录则只返回队列。"""
    if not archive.list_by_user(session, user_id=user.id):
        grant = store.load_grant(str(user.id))
        if not grant:
            raise BizException("授权已过期，请重新登录", code=BizCode.UNAUTHORIZED)
        contents = HttpxUserDataClient(get_app_settings()).list_contents(grant)
        archive.discover_listed_contents(session, user_id=user.id, contents=contents)
    return ApiResponse.success(_queue_view(session, archive, store, user))


@router.get("/me/articles/queue")
def list_archive_queue(
    session: SessionDep,
    archive: CollectDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[ArchiveQueueView]:
    return ApiResponse.success(_queue_view(session, archive, store, user))


@router.get("/me/articles/failed-fetch")
def list_failed_fetch(
    session: SessionDep,
    archive: CollectDep,
    store: StoreDep,
    user: UserDep,
) -> ApiResponse[FailedFetchListView]:
    return ApiResponse.success(_failed_list(session, archive, store, user))


@router.post("/me/articles/browser-capture")
def capture_from_browser(
    body: BrowserCaptureBody,
    session: SessionDep,
    archive: CollectDep,
    store: StoreDep,
) -> ApiResponse[ArticleArchiveView]:
    user_id = store.user_id_for_capture(body.token)
    if not user_id:
        raise BizException("补抓凭证无效或已过期", code=BizCode.UNAUTHORIZED)
    user = session.get(User, uuid.UUID(user_id))
    if user is None:
        raise BizException("补抓凭证无效或已过期", code=BizCode.UNAUTHORIZED)
    row = archive.capture_from_browser(
        session,
        user_id=user.id,
        source_url=body.source_url,
        html=body.html,
        title=body.title,
    )
    return ApiResponse.success(_view(row))
