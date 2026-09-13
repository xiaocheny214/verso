"""知乎登录与当前用户。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from verso_common.enums import StrengthTag
from verso_common.models import UserCard
from verso_common.result import Response as ApiResponse
from verso_framework.config import get_app_settings

from verso_app.server.identity.models import User
from verso_app.server.identity.service import IdentityService
from verso_app.web.middleware.auth import get_current_user, get_identity_service

router = APIRouter(tags=["identity"])

IdentityDep = Annotated[IdentityService, Depends(get_identity_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class SelfReportBody(BaseModel):
    tags: list[StrengthTag] = Field(min_length=1, max_length=3)


def _set_intent_cookie(response: JSONResponse, nonce: str) -> None:
    settings = get_app_settings()
    response.set_cookie(
        key="verso_oauth_intent",
        value=nonce,
        max_age=settings.oauth_intent_ttl_sec,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _set_session_cookie(response: RedirectResponse, session_id: str) -> None:
    settings = get_app_settings()
    response.set_cookie(
        key=settings.session_cookie,
        value=session_id,
        max_age=settings.session_ttl_sec,
        httponly=True,
        samesite="lax",
        path="/",
    )


@router.get("/auth/zhihu/url")
def zhihu_login_url(identity: IdentityDep) -> JSONResponse:
    started = identity.start_login()
    payload = ApiResponse.success({"authorize_url": started.authorize_url}).model_dump(
        mode="json"
    )
    response = JSONResponse(payload)
    _set_intent_cookie(response, started.nonce)
    return response


@router.get("/auth/zhihu/callback")
def zhihu_callback(
    identity: IdentityDep,
    request: Request,
    authorization_code: str | None = None,
    code: str | None = None,
) -> RedirectResponse:
    auth_code = authorization_code or code or ""
    nonce = request.cookies.get("verso_oauth_intent") or ""
    result = identity.complete_login(code=auth_code, nonce=nonce)
    target = get_app_settings().public_origin.rstrip("/") + "/"
    response = RedirectResponse(url=target, status_code=302)
    _set_session_cookie(response, result.session_id)
    response.delete_cookie("verso_oauth_intent", path="/")
    return response


@router.post("/auth/logout")
def logout(request: Request, identity: IdentityDep) -> JSONResponse:
    settings = get_app_settings()
    identity.logout(request.cookies.get(settings.session_cookie) or "")
    response = JSONResponse(ApiResponse.success().model_dump(mode="json"))
    response.delete_cookie(settings.session_cookie, path="/")
    return response


@router.get("/me")
def me(identity: IdentityDep, user: UserDep) -> ApiResponse[UserCard]:
    return ApiResponse.success(identity.get_card(user))


@router.post("/me/portrait/sync")
def sync_portrait(identity: IdentityDep, user: UserDep) -> ApiResponse[UserCard]:
    identity.sync_portrait(user.id)
    return ApiResponse.success(identity.get_card(user))


@router.post("/me/portrait/self-report")
def self_report(
    body: SelfReportBody,
    identity: IdentityDep,
    user: UserDep,
) -> ApiResponse[UserCard]:
    return ApiResponse.success(identity.self_report(user, body.tags))
