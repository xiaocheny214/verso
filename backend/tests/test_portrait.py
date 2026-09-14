from datetime import UTC, datetime, timedelta

import pytest
from fakes import FakeOAuth, FakeRedis, FakeZhihu
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from verso_app.server.auth.models import User  # noqa: F401
from verso_app.server.auth.service import AuthService
from verso_app.server.auth.session_store import SessionStore
from verso_app.server.portrait.models import Portrait
from verso_app.server.portrait.service import PortraitService
from verso_app.server.portrait.tagger import tags_from_text
from verso_app.server.reputation.service import ReputationService
from verso_common.enums import BizCode, PortraitHorizon, PortraitSource, StrengthTag
from verso_common.exceptions import BizException
from verso_framework.config.app import AppSettings
from verso_framework.db.base import Base
from verso_framework.providers.zhihu import ZhihuCollection, ZhihuContent, ZhihuProfile


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
    redis: FakeRedis,
    profile: ZhihuProfile | None = None,
) -> AuthService:
    return AuthService(
        session=db,
        store=SessionStore(redis),
        oauth=FakeOAuth(profile or ZhihuProfile(url_token="alice", name="Alice")),
        reputation=ReputationService(),
        settings=settings,
    )


def _portrait(db: Session, redis: FakeRedis, zhihu: FakeZhihu | None = None) -> PortraitService:
    return PortraitService(
        session=db,
        grants=SessionStore(redis),
        zhihu=zhihu or FakeZhihu(),
    )


def test_tags_from_programming_title() -> None:
    assert StrengthTag.PROGRAMMING in tags_from_text("Python 后端怎么入门")


def test_portrait_splits_stable_and_recent(db: Session, settings: AppSettings) -> None:
    now = datetime.now(UTC)
    old = int((now - timedelta(days=30)).timestamp())
    fresh = int((now - timedelta(days=1)).timestamp())
    redis = FakeRedis()
    zhihu = FakeZhihu(
        contents=[
            ZhihuContent("Python 开发笔记", "", "https://x/1", "article", old),
            ZhihuContent("徒手健身入门", "", "https://x/2", "article", fresh),
        ]
    )
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="abc", nonce=auth.start_login().nonce).user
    _portrait(db, redis, zhihu).sync(user.id)
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    recent = db.get(Portrait, (user.id, PortraitHorizon.RECENT_7D.value))
    assert stable is not None
    assert recent is not None
    assert StrengthTag.PROGRAMMING.value in stable.strengths
    assert StrengthTag.FITNESS.value in stable.strengths
    assert StrengthTag.FITNESS.value in recent.strengths
    assert StrengthTag.PROGRAMMING.value not in recent.strengths
    assert stable.source == PortraitSource.CONTENTS


def test_self_report_when_empty(db: Session, settings: AppSettings) -> None:
    redis = FakeRedis()
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="a", nonce=auth.start_login().nonce).user
    card = _portrait(db, redis).self_report(user, [StrengthTag.FITNESS])
    stable = next(item for item in card.portraits if item.horizon == PortraitHorizon.STABLE)
    assert stable.strengths[0].tag == StrengthTag.FITNESS
    assert stable.strengths[0].source == PortraitSource.SELF_REPORTED


def test_self_report_rejected_when_contents_exist(db: Session, settings: AppSettings) -> None:
    redis = FakeRedis()
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
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="a", nonce=auth.start_login().nonce).user
    portrait = _portrait(db, redis, zhihu)
    portrait.sync(user.id)
    with pytest.raises(BizException) as exc:
        portrait.self_report(user, [StrengthTag.FITNESS])
    assert exc.value.code == BizCode.CONFLICT


def test_portrait_from_favorites_when_no_posts(db: Session, settings: AppSettings) -> None:
    now = int(datetime.now(UTC).timestamp())
    redis = FakeRedis()
    zhihu = FakeZhihu(
        collections=[
            ZhihuCollection("徒手健身入门", "", "https://x/fav", now, extra_text="力量训练")
        ]
    )
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="a", nonce=auth.start_login().nonce).user
    portrait = _portrait(db, redis, zhihu)
    portrait.sync(user.id)
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    recent = db.get(Portrait, (user.id, PortraitHorizon.RECENT_7D.value))
    assert stable is not None
    assert StrengthTag.FITNESS.value in stable.strengths
    assert stable.source == PortraitSource.FAVORITES
    assert recent is not None
    assert StrengthTag.FITNESS.value in recent.strengths
    assert recent.source == PortraitSource.FAVORITES
    with pytest.raises(BizException) as exc:
        portrait.self_report(user, [StrengthTag.PROGRAMMING])
    assert exc.value.code == BizCode.CONFLICT


def test_contents_failure_still_uses_favorites(db: Session, settings: AppSettings) -> None:
    class ContentsDown(FakeZhihu):
        def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]:
            raise RuntimeError("contents down")

    now = int(datetime.now(UTC).timestamp())
    redis = FakeRedis()
    zhihu = ContentsDown(
        collections=[ZhihuCollection("Python 开发笔记", "", "https://x/fav", now)]
    )
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="a", nonce=auth.start_login().nonce).user
    _portrait(db, redis, zhihu).sync(user.id)
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    assert stable is not None
    assert StrengthTag.PROGRAMMING.value in stable.strengths
    assert stable.source == PortraitSource.FAVORITES


def test_fetch_failure_keeps_portrait_and_blocks_self_report(
    db: Session, settings: AppSettings
) -> None:
    now = int(datetime.now(UTC).timestamp())
    redis = FakeRedis()
    zhihu = FakeZhihu(
        contents=[
            ZhihuContent("Python 开发笔记", "", "https://x/1", "article", now)
        ]
    )
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="a", nonce=auth.start_login().nonce).user
    portrait = _portrait(db, redis, zhihu)
    portrait.sync(user.id)
    stable = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    assert stable is not None
    assert StrengthTag.PROGRAMMING.value in stable.strengths

    def boom(*_args, **_kwargs):
        raise RuntimeError("zhihu down")

    zhihu.list_contents = boom
    zhihu.list_followees = boom
    zhihu.list_favorites = boom
    with pytest.raises(BizException) as sync_exc:
        portrait.sync(user.id)
    assert sync_exc.value.code == BizCode.INTERNAL_ERROR
    kept = db.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
    assert kept is not None
    assert StrengthTag.PROGRAMMING.value in kept.strengths
    assert kept.source == PortraitSource.CONTENTS
    with pytest.raises(BizException) as report_exc:
        portrait.self_report(user, [StrengthTag.FITNESS])
    assert report_exc.value.code == BizCode.CONFLICT


def test_empty_zhihu_data_still_allows_self_report(db: Session, settings: AppSettings) -> None:
    redis = FakeRedis()
    auth = _auth(db, settings, redis=redis)
    user = auth.complete_login(code="a", nonce=auth.start_login().nonce).user
    card = _portrait(db, redis).self_report(user, [StrengthTag.FITNESS])
    stable = next(item for item in card.portraits if item.horizon == PortraitHorizon.STABLE)
    assert stable.strengths[0].tag == StrengthTag.FITNESS
    assert stable.strengths[0].source == PortraitSource.SELF_REPORTED
