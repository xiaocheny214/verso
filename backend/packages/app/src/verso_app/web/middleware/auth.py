"""当前登录用户。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.auth.service import AuthService
from verso_app.server.auth.session_store import SessionStore
from verso_app.server.exchange.service import ExchangeService
from verso_app.server.match.compatibility import build_pair_compatibility_evaluator
from verso_app.server.match.service import MatchService
from verso_app.server.portrait.extractor import build_evidence_classifier
from verso_app.server.portrait.service import PortraitService
from verso_app.server.quality.judge import build_judge
from verso_app.server.quality.service import QualityService
from verso_app.server.reputation.service import ReputationService
from verso_framework.config import get_app_settings
from verso_framework.db import get_redis, get_session
from verso_framework.providers.zhihu import HttpxOAuthClient, HttpxUserDataClient

SessionDep = Annotated[Session, Depends(get_session)]


def get_reputation_service() -> ReputationService:
    return ReputationService(settings=get_app_settings())


def get_auth_service(session: SessionDep) -> AuthService:
    settings = get_app_settings()
    return AuthService(
        session=session,
        store=SessionStore(get_redis()),
        oauth=HttpxOAuthClient(settings),
        reputation=ReputationService(settings=settings),
        settings=settings,
    )


def get_portrait_service(session: SessionDep) -> PortraitService:
    settings = get_app_settings()
    return PortraitService(
        session=session,
        grants=SessionStore(get_redis()),
        zhihu=HttpxUserDataClient(settings),
        classifier=build_evidence_classifier(settings),
    )


AuthDep = Annotated[AuthService, Depends(get_auth_service)]
PortraitDep = Annotated[PortraitService, Depends(get_portrait_service)]


def get_match_service(session: SessionDep) -> MatchService:
    settings = get_app_settings()
    return MatchService(
        session=session,
        exchange=ExchangeService(session),
        reputation=ReputationService(settings=settings),
        compatibility=build_pair_compatibility_evaluator(settings),
    )


def get_exchange_service(session: SessionDep) -> ExchangeService:
    return ExchangeService(session)


def get_quality_service(session: SessionDep) -> QualityService:
    settings = get_app_settings()
    return QualityService(
        session,
        exchange=ExchangeService(session),
        reputation=ReputationService(settings=settings),
        judge=build_judge(settings),
    )


def get_current_user(request: Request, auth: AuthDep) -> User:
    return auth.require_user(request.cookies.get(get_app_settings().session_cookie))
