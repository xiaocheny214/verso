"""当前用户查询术语归一化映射路由。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.term_mapping.models import QueryTermMapping
from verso_app.server.term_mapping.service import _UNSET, QueryTermMappingService
from verso_app.web.middleware.auth import get_current_user, get_term_mapping_service
from verso_common.models import QueryTermMappingView
from verso_common.result import ListResponse
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["term_mapping"])

TermMappingDep = Annotated[QueryTermMappingService, Depends(get_term_mapping_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class QueryTermMappingCreateBody(BaseModel):
    source_term: str = Field(min_length=1, max_length=128)
    target_term: str = Field(min_length=1, max_length=128)
    match_type: int = 1
    priority: int = 0
    enabled: bool = True
    remark: str | None = None


class QueryTermMappingPatchBody(BaseModel):
    source_term: str | None = Field(default=None, min_length=1, max_length=128)
    target_term: str | None = Field(default=None, min_length=1, max_length=128)
    match_type: int | None = None
    priority: int | None = None
    enabled: bool | None = None
    remark: str | None = None


def _mapping_view(row: QueryTermMapping) -> QueryTermMappingView:
    return QueryTermMappingView(
        id=str(row.id),
        user_id=str(row.user_id),
        source_term=row.source_term,
        target_term=row.target_term,
        match_type=row.match_type,
        priority=row.priority,
        enabled=row.enabled,
        remark=row.remark,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/me/term-mappings")
def create_term_mapping(
    body: QueryTermMappingCreateBody,
    service: TermMappingDep,
    user: UserDep,
) -> ApiResponse[QueryTermMappingView]:
    row = service.create(
        user_id=user.id,
        source_term=body.source_term,
        target_term=body.target_term,
        match_type=body.match_type,
        priority=body.priority,
        enabled=body.enabled,
        remark=body.remark,
    )
    return ApiResponse.success(_mapping_view(row))


@router.patch("/me/term-mappings/{mapping_id}")
def patch_term_mapping(
    mapping_id: uuid.UUID,
    body: QueryTermMappingPatchBody,
    service: TermMappingDep,
    user: UserDep,
) -> ApiResponse[QueryTermMappingView]:
    fields = body.model_fields_set
    row = service.update(
        user_id=user.id,
        mapping_id=mapping_id,
        source_term=body.source_term if "source_term" in fields else None,
        target_term=body.target_term if "target_term" in fields else None,
        match_type=body.match_type if "match_type" in fields else None,
        priority=body.priority if "priority" in fields else None,
        enabled=body.enabled if "enabled" in fields else None,
        remark=body.remark if "remark" in fields else _UNSET,
    )
    return ApiResponse.success(_mapping_view(row))


@router.delete("/me/term-mappings/{mapping_id}")
def delete_term_mapping(
    mapping_id: uuid.UUID,
    service: TermMappingDep,
    user: UserDep,
) -> ApiResponse[None]:
    service.delete(user_id=user.id, mapping_id=mapping_id)
    return ApiResponse.success()


@router.get("/me/term-mappings")
def list_term_mappings(
    service: TermMappingDep,
    user: UserDep,
    keyword: str | None = None,
    enabled: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ListResponse[QueryTermMappingView]:
    items, total = service.list_mappings(
        user_id=user.id,
        keyword=keyword,
        enabled=enabled,
        page=page,
        page_size=page_size,
    )
    return ListResponse.success(
        [_mapping_view(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/me/term-mappings/{mapping_id}")
def get_term_mapping(
    mapping_id: uuid.UUID,
    service: TermMappingDep,
    user: UserDep,
) -> ApiResponse[QueryTermMappingView]:
    row = service.get(user_id=user.id, mapping_id=mapping_id)
    return ApiResponse.success(_mapping_view(row))
