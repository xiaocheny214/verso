"""当前用户成色。只读。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from verso_common.models import ReputationView
from verso_common.result import Response as ApiResponse

from verso_app.server.auth.models import User
from verso_app.server.reputation.service import ReputationService
from verso_app.web.middleware.auth import (
    SessionDep,
    get_current_user,
    get_reputation_service,
)

router = APIRouter(tags=["reputation"])

ReputationDep = Annotated[ReputationService, Depends(get_reputation_service)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/me/reputation")
def me_reputation(
    session: SessionDep,
    reputation: ReputationDep,
    user: UserDep,
) -> ApiResponse[ReputationView]:
    return ApiResponse.success(reputation.get_view(session, user.id))
