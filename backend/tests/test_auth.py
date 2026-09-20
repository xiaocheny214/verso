from uuid import UUID

import pytest
from fakes import FakeOAuth, FakeRedis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.server.auth.models import User
from verso_app.server.auth.service import AuthService
from verso_app.server.auth.session_store import SessionStore
from verso_app.server.portrait.models import Portrait
from verso_app.server.reputation.models import Reputation
from verso_app.server.reputation.service import ReputationService
from verso_app.web.api.auth import router as auth_router
from verso_app.web.handler import register_exception_handlers
from verso_app.web.middleware.auth import get_auth_service, get_portrait_service
from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_framework.config.app import AppSettings
from verso_framework.db.base import Base
from verso_framework.providers.zhihu import ZhihuProfile


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def settings() -> AppSettings:
    return AppSettings(
        zhihu_client_id="app",
        zhihu_client_secret="secret",
        zhihu_access_secret="platform-secret",
        zhihu_redirect_uri="http://localhost:8000/auth/zhihu/callback",
        public_origin="http://localhost:3000",
        create_tables=False,
    )


def _auth(
    db: Session,
    settings: AppSettings,
    *,
    profile: ZhihuProfile | None = None,
    redis: FakeRedis | None = None,
) -> AuthService:
    return AuthService(
        session=db,
        store=SessionStore(redis or FakeRedis()),
        oauth=FakeOAuth(profile or ZhihuProfile(url_token="alice", name="Alice")),
        reputation=ReputationService(),
        settings=settings,
    )


def test_login_upserts_user_and_opens_reputation(db: Session, settings: AppSettings) -> None:
    service = _auth(db, settings)
    started = service.start_login()
    result = service.complete_login(code="abc", nonce=started.nonce)
    assert result.user.display_name == "Alice"
    again = service.complete_login(code="abc", nonce=service.start_login().nonce)
    assert again.user.id == result.user.id
    assert len(db.scalars(select(User)).all()) == 1
    score = db.get(Reputation, result.user.id)
    assert score is not None
    assert score.score == REPUTATION_INITIAL_SCORE


def test_login_does_not_write_portraits(db: Session, settings: AppSettings) -> None:
    service = _auth(db, settings)
    user = service.complete_login(code="abc", nonce=service.start_login().nonce).user
    assert db.scalars(select(Portrait).where(Portrait.user_id == user.id)).all() == []


def test_second_browser_kicks_old_session(db: Session, settings: AppSettings) -> None:
    redis = FakeRedis()
    service = _auth(db, settings, redis=redis)
    first = service.complete_login(code="a", nonce=service.start_login().nonce)
    second = service.complete_login(code="a", nonce=service.start_login().nonce)
    with pytest.raises(BizException) as exc:
        service.require_user(first.session_id)
    assert exc.value.code == BizCode.UNAUTHORIZED
    assert service.require_user(second.session_id).id == second.user.id


def test_login_url_sets_intent_cookie(db: Session, settings: AppSettings) -> None:
    service = _auth(db, settings)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.dependency_overrides[get_auth_service] = lambda: service
    client = TestClient(app)
    response = client.get("/auth/zhihu/url")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert "authorize_url" in body["data"]
    assert "verso_oauth_intent" in response.cookies


def test_callback_uses_state_when_intent_cookie_missing(
    db: Session, settings: AppSettings, monkeypatch
) -> None:
    monkeypatch.setattr("verso_app.web.api.auth.get_app_settings", lambda: settings)
    service = _auth(db, settings)
    started = service.start_login()

    class QuietPortrait:
        def sync(self, user_id) -> None:
            return None

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.dependency_overrides[get_auth_service] = lambda: service
    app.dependency_overrides[get_portrait_service] = lambda: QuietPortrait()
    client = TestClient(app)
    response = client.get(
        "/auth/zhihu/callback",
        params={"state": started.nonce, "authorization_code": "abc"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/"


def test_user_id_is_uuid(db: Session, settings: AppSettings) -> None:
    service = _auth(db, settings)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    UUID(str(user.id))
