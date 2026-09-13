from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.server.identity.models import Portrait, User
from verso_app.server.identity.service import IdentityService
from verso_app.server.identity.session_store import SessionStore
from verso_app.server.identity.tagger import tags_from_text
from verso_app.server.reputation.models import Reputation
from verso_app.server.reputation.service import ReputationService
from verso_app.web.api.auth import router as auth_router
from verso_app.web.handler import register_exception_handlers
from verso_app.web.middleware.auth import get_identity_service
from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import BizCode, PortraitHorizon, PortraitSource, StrengthTag
from verso_common.exceptions import BizException
from verso_framework.config.app import AppSettings
from verso_framework.db.base import Base
from verso_framework.providers.zhihu import (
    ZhihuCollection,
    ZhihuContent,
    ZhihuFollowee,
    ZhihuProfile,
    ZhihuToken,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name: str, value: str, ex: int | None = None) -> None:
        self.values[name] = value

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def getdel(self, name: str) -> str | None:
        return self.values.pop(name, None)

    def delete(self, *names: str) -> None:
        for name in names:
            self.values.pop(name, None)


class FakeOAuth:
    def __init__(self, profile: ZhihuProfile) -> None:
        self.profile = profile
        self.codes: list[str] = []

    def authorization_url(self, state: str) -> str:
        return f"https://openapi.zhihu.com/authorize?state={state}"

    def exchange_code(self, code: str) -> ZhihuToken:
        self.codes.append(code)
        return ZhihuToken(access_token="tok", expires_in=3600)

    def fetch_profile(self, access_token: str) -> ZhihuProfile:
        return self.profile


class FakeZhihu:
    def __init__(
        self,
        contents: list[ZhihuContent] | None = None,
        followees: list[ZhihuFollowee] | None = None,
        collections: list[ZhihuCollection] | None = None,
    ) -> None:
        self.contents = contents or []
        self.followees = followees or []
        self.collections = collections or []

    def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]:
        return self.contents

    def list_followees(self, access_token: str, *, limit: int = 20) -> list[ZhihuFollowee]:
        return self.followees

    def list_favorites(self, access_token: str, *, limit: int = 50) -> list[ZhihuCollection]:
        return self.collections


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


def _service(
    db: Session,
    settings: AppSettings,
    *,
    profile: ZhihuProfile | None = None,
    zhihu: FakeZhihu | None = None,
    redis: FakeRedis | None = None,
) -> IdentityService:
    return IdentityService(
        session=db,
        store=SessionStore(redis or FakeRedis()),
        oauth=FakeOAuth(profile or ZhihuProfile(url_token="alice", name="Alice")),
        zhihu=zhihu or FakeZhihu(),
        reputation=ReputationService(),
        settings=settings,
    )


def test_tags_from_programming_title() -> None:
    assert StrengthTag.PROGRAMMING in tags_from_text("Python 后端怎么入门")


def test_login_upserts_user_and_opens_reputation(db: Session, settings: AppSettings) -> None:
    service = _service(db, settings)
    started = service.start_login()
    result = service.complete_login(code="abc", nonce=started.nonce)
    assert result.user.display_name == "Alice"
    again = service.complete_login(code="abc", nonce=service.start_login().nonce)
    assert again.user.id == result.user.id
    assert len(db.scalars(select(User)).all()) == 1
    score = db.get(Reputation, result.user.id)
    assert score is not None
    assert score.score == REPUTATION_INITIAL_SCORE


def test_portrait_splits_stable_and_recent(db: Session, settings: AppSettings) -> None:
    now = datetime.now(UTC)
    old = int((now - timedelta(days=30)).timestamp())
    fresh = int((now - timedelta(days=1)).timestamp())
    zhihu = FakeZhihu(
        contents=[
            ZhihuContent("Python 开发笔记", "", "https://x/1", "article", old),
            ZhihuContent("徒手健身入门", "", "https://x/2", "article", fresh),
        ]
    )
    service = _service(db, settings, zhihu=zhihu)
    started = service.start_login()
    user = service.complete_login(code="abc", nonce=started.nonce).user
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    recent = db.get(Portrait, (user.id, PortraitHorizon.RECENT_7D.value))
    assert stable is not None
    assert recent is not None
    assert StrengthTag.PROGRAMMING.value in stable.strengths
    assert StrengthTag.FITNESS.value in stable.strengths
    assert StrengthTag.FITNESS.value in recent.strengths
    assert StrengthTag.PROGRAMMING.value not in recent.strengths
    assert stable.source == PortraitSource.CONTENTS


def test_second_browser_kicks_old_session(db: Session, settings: AppSettings) -> None:
    redis = FakeRedis()
    service = _service(db, settings, redis=redis)
    first = service.complete_login(code="a", nonce=service.start_login().nonce)
    second = service.complete_login(code="a", nonce=service.start_login().nonce)
    with pytest.raises(BizException) as exc:
        service.require_user(first.session_id)
    assert exc.value.code == BizCode.UNAUTHORIZED
    assert service.require_user(second.session_id).id == second.user.id


def test_self_report_when_empty(db: Session, settings: AppSettings) -> None:
    service = _service(db, settings)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    card = service.self_report(user, [StrengthTag.FITNESS])
    stable = next(item for item in card.portraits if item.horizon == PortraitHorizon.STABLE)
    assert stable.strengths[0].tag == StrengthTag.FITNESS
    assert stable.strengths[0].source == PortraitSource.SELF_REPORTED


def test_self_report_rejected_when_contents_exist(db: Session, settings: AppSettings) -> None:
    zhihu = FakeZhihu(
        contents=[
            ZhihuContent(
                "Python 开发笔记",
                "",
                "https://x/1",
                "article",
                int(datetime.now(UTC).timestamp()),
            )
        ]
    )
    service = _service(db, settings, zhihu=zhihu)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    with pytest.raises(BizException) as exc:
        service.self_report(user, [StrengthTag.FITNESS])
    assert exc.value.code == BizCode.CONFLICT


def test_login_url_sets_intent_cookie(db: Session, settings: AppSettings) -> None:
    service = _service(db, settings)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.dependency_overrides[get_identity_service] = lambda: service
    client = TestClient(app)
    response = client.get("/auth/zhihu/url")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert "authorize_url" in body["data"]
    assert "verso_oauth_intent" in response.cookies


def test_portrait_from_favorites_when_no_posts(db: Session, settings: AppSettings) -> None:
    now = int(datetime.now(UTC).timestamp())
    zhihu = FakeZhihu(
        collections=[
            ZhihuCollection("徒手健身入门", "", "https://x/fav", now, extra_text="力量训练")
        ]
    )
    service = _service(db, settings, zhihu=zhihu)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    recent = db.get(Portrait, (user.id, PortraitHorizon.RECENT_7D.value))
    assert stable is not None
    assert StrengthTag.FITNESS.value in stable.strengths
    assert stable.source == PortraitSource.FAVORITES
    assert recent is not None
    assert StrengthTag.FITNESS.value in recent.strengths
    assert recent.source == PortraitSource.FAVORITES
    with pytest.raises(BizException) as exc:
        service.self_report(user, [StrengthTag.PROGRAMMING])
    assert exc.value.code == BizCode.CONFLICT


def test_contents_failure_still_uses_favorites(db: Session, settings: AppSettings) -> None:
    class ContentsDown(FakeZhihu):
        def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]:
            raise RuntimeError("contents down")

    now = int(datetime.now(UTC).timestamp())
    zhihu = ContentsDown(
        collections=[ZhihuCollection("Python 开发笔记", "", "https://x/fav", now)]
    )
    service = _service(db, settings, zhihu=zhihu)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    assert stable is not None
    assert StrengthTag.PROGRAMMING.value in stable.strengths
    assert stable.source == PortraitSource.FAVORITES


def test_fetch_failure_keeps_portrait_and_blocks_self_report(
    db: Session, settings: AppSettings
) -> None:
    now = int(datetime.now(UTC).timestamp())
    zhihu = FakeZhihu(
        contents=[
            ZhihuContent("Python 开发笔记", "", "https://x/1", "article", now)
        ]
    )
    service = _service(db, settings, zhihu=zhihu)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    assert stable is not None
    assert StrengthTag.PROGRAMMING.value in stable.strengths

    def boom(*_args, **_kwargs):
        raise RuntimeError("zhihu down")

    zhihu.list_contents = boom
    zhihu.list_followees = boom
    zhihu.list_favorites = boom
    with pytest.raises(BizException) as sync_exc:
        service.sync_portrait(user.id)
    assert sync_exc.value.code == BizCode.INTERNAL_ERROR
    kept = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    assert kept is not None
    assert StrengthTag.PROGRAMMING.value in kept.strengths
    assert kept.source == PortraitSource.CONTENTS
    with pytest.raises(BizException) as report_exc:
        service.self_report(user, [StrengthTag.FITNESS])
    assert report_exc.value.code == BizCode.CONFLICT


def test_empty_zhihu_data_still_allows_self_report(db: Session, settings: AppSettings) -> None:
    service = _service(db, settings, zhihu=FakeZhihu())
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    card = service.self_report(user, [StrengthTag.FITNESS])
    stable = next(item for item in card.portraits if item.horizon == PortraitHorizon.STABLE)
    assert stable.strengths[0].tag == StrengthTag.FITNESS
    assert stable.strengths[0].source == PortraitSource.SELF_REPORTED


def test_user_id_is_uuid(db: Session, settings: AppSettings) -> None:
    service = _service(db, settings)
    user = service.complete_login(code="a", nonce=service.start_login().nonce).user
    UUID(str(user.id))
