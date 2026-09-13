"""人先触发的回答评估。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from verso_common.models import ReviewView
from verso_common.result import Response as ApiResponse

from verso_app.server.identity.models import User
from verso_app.server.quality.service import QualityService
from verso_app.web.middleware.auth import get_current_user, get_quality_service

router = APIRouter(tags=["quality"])

QualityDep = Annotated[QualityService, Depends(get_quality_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class CreateReviewBody(BaseModel):
    exchange_id: UUID


@router.post("/reviews")
def create_review(
    body: CreateReviewBody,
    quality: QualityDep,
    user: UserDep,
) -> ApiResponse[ReviewView]:
    return ApiResponse.success(quality.submit(user, body.exchange_id))
