"""当前登录用户。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session
from verso_framework.config import get_app_settings
from verso_framework.db import get_redis, get_session
from verso_framework.providers.zhihu import HttpxOAuthClient, HttpxUserDataClient

from verso_app.server.exchange.service import ExchangeService
from verso_app.server.identity.models import User
from verso_app.server.identity.service import IdentityService
from verso_app.server.identity.session_store import SessionStore
from verso_app.server.match.service import MatchService
from verso_app.server.quality.judge import build_judge
from verso_app.server.quality.service import QualityService
from verso_app.server.reputation.service import ReputationService

SessionDep = Annotated[Session, Depends(get_session)]


def get_identity_service(session: SessionDep) -> IdentityService:
    settings = get_app_settings()
    return IdentityService(
        session=session,
        store=SessionStore(get_redis()),
        oauth=HttpxOAuthClient(settings),
        zhihu=HttpxUserDataClient(settings),
        reputation=ReputationService(),
        settings=settings,
    )


IdentityDep = Annotated[IdentityService, Depends(get_identity_service)]


def get_match_service(session: SessionDep) -> MatchService:
    return MatchService(session=session, exchange=ExchangeService(session))


def get_exchange_service(session: SessionDep) -> ExchangeService:
    return ExchangeService(session)


def get_quality_service(session: SessionDep) -> QualityService:
    return QualityService(
        session,
        exchange=ExchangeService(session),
        reputation=ReputationService(),
        judge=build_judge(get_app_settings()),
    )


def get_current_user(request: Request, identity: IdentityDep) -> User:
    return identity.require_user(request.cookies.get(get_app_settings().session_cookie))
