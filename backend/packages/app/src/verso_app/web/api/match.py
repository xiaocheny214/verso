"""这次想学什么与配对。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.match.service import MatchService
from verso_app.web.middleware.auth import get_current_user, get_match_service
from verso_common.enums import StrengthTag
from verso_common.models import MatchConditionView
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["match"])

MatchDep = Annotated[MatchService, Depends(get_match_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class SubmitConditionBody(BaseModel):
    want_text: str = Field(min_length=1, max_length=200)
    want_tag: StrengthTag


@router.post("/match/conditions")
def submit_condition(
    body: SubmitConditionBody,
    match: MatchDep,
    user: UserDep,
) -> ApiResponse[MatchConditionView]:
    return ApiResponse.success(match.submit(user, want_text=body.want_text, want_tag=body.want_tag))


@router.get("/match/conditions/me")
def current_condition(match: MatchDep, user: UserDep) -> ApiResponse[MatchConditionView]:
    return ApiResponse.success(match.current(user))


@router.post("/match/conditions/cancel")
def cancel_condition(match: MatchDep, user: UserDep) -> ApiResponse[MatchConditionView]:
    return ApiResponse.success(match.cancel(user))
