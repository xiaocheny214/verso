"""知乎登录与当前用户。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from verso_app.server.auth.models import User
from verso_app.server.auth.service import AuthService
from verso_app.server.portrait.service import PortraitService
from verso_app.web.middleware.auth import (
    get_auth_service,
    get_current_user,
    get_portrait_service,
)
from verso_common.models import UserCard
from verso_common.result import Response as ApiResponse
from verso_framework.config import get_app_settings

logger = logging.getLogger("verso.web.auth")

router = APIRouter(tags=["auth"])

AuthDep = Annotated[AuthService, Depends(get_auth_service)]
PortraitDep = Annotated[PortraitService, Depends(get_portrait_service)]
UserDep = Annotated[User, Depends(get_current_user)]


class AuthorizeUrlData(BaseModel):
    authorize_url: str


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


@router.get("/auth/zhihu/url", response_model=ApiResponse[AuthorizeUrlData])
def zhihu_login_url(auth: AuthDep) -> JSONResponse:
    started = auth.start_login()
    payload = ApiResponse.success({"authorize_url": started.authorize_url}).model_dump(mode="json")
    response = JSONResponse(payload)
    _set_intent_cookie(response, started.nonce)
    return response


@router.get("/auth/zhihu/callback", response_class=RedirectResponse, status_code=302)
def zhihu_callback(
    auth: AuthDep,
    portrait: PortraitDep,
    request: Request,
    authorization_code: str | None = None,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    auth_code = authorization_code or code or ""
    nonce = request.cookies.get("verso_oauth_intent") or state or ""
    result = auth.complete_login(code=auth_code, nonce=nonce)
    try:
        if portrait.enqueue_if_stale(result.user.id):
            logger.info("画像已入队异步同步 user_id=%s", result.user.id)
    except Exception:
        logger.exception("画像入队失败 user_id=%s", result.user.id)
    target = get_app_settings().public_origin.rstrip("/") + "/"
    response = RedirectResponse(url=target, status_code=302)
    _set_session_cookie(response, result.session_id)
    response.delete_cookie("verso_oauth_intent", path="/")
    return response


@router.post("/auth/logout", response_model=ApiResponse[None])
def logout(request: Request, auth: AuthDep) -> JSONResponse:
    settings = get_app_settings()
    auth.logout(request.cookies.get(settings.session_cookie) or "")
    response = JSONResponse(ApiResponse.success().model_dump(mode="json"))
    response.delete_cookie(settings.session_cookie, path="/")
    return response


@router.get("/me")
def me(portrait: PortraitDep, user: UserDep) -> ApiResponse[UserCard]:
    return ApiResponse.success(portrait.card_for(user))
