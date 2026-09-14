"""当前用户画像同步与自报。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.portrait.service import PortraitService
from verso_app.web.middleware.auth import get_current_user, get_portrait_service
from verso_common.enums import StrengthTag
from verso_common.models import UserCard
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["portrait"])

PortraitDep = Annotated[PortraitService, Depends(get_portrait_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class SelfReportBody(BaseModel):
    tags: list[StrengthTag] = Field(min_length=1, max_length=3)


@router.post("/me/portrait/sync")
def sync_portrait(portrait: PortraitDep, user: UserDep) -> ApiResponse[UserCard]:
    portrait.sync(user.id)
    return ApiResponse.success(portrait.card_for(user))


@router.post("/me/portrait/self-report")
def self_report(
    body: SelfReportBody,
    portrait: PortraitDep,
    user: UserDep,
) -> ApiResponse[UserCard]:
    return ApiResponse.success(portrait.self_report(user, body.tags))
