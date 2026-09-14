from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from verso_app.server.auth.models import User
from verso_app.server.match.service import MatchService
from verso_app.server.portrait.models import Portrait
from verso_app.server.reputation.models import Reputation
from verso_app.server.reputation.service import ReputationService
from verso_app.web.api.reputation import router as reputation_router
from verso_app.web.handler import register_exception_handlers
from verso_app.web.middleware.auth import get_current_user, get_reputation_service
from verso_common.constants import (
    REPUTATION_GOOD_DELTA,
    REPUTATION_INITIAL_SCORE,
    REPUTATION_MIN_ACTIVE_SCORE,
    REPUTATION_POOR_DELTA,
    REPUTATION_SCORE_MAX,
)
from verso_common.enums import (
    BizCode,
    Eligibility,
    MatchConditionStatus,
    PortraitHorizon,
    PortraitSource,
    StrengthTag,
    UserStatus,
)
from verso_common.exceptions import BizException
from verso_framework.config.app import AppSettings
from verso_framework.db import get_session
from verso_framework.db.base import Base


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


def _user(db: Session, *, name: str, score: int | None = None) -> User:
    now = datetime.now(UTC)
    user = User(
        zhihu_url_token=name.lower(),
        display_name=name,
        status=UserStatus.ACTIVE,
        last_login_at=now,
    )
    db.add(user)
    db.flush()
    db.add(
        Portrait(
            user_id=user.id,
            kind=PortraitHorizon.STABLE.value,
            strengths=[StrengthTag.PROGRAMMING.value],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=now,
        )
    )
    db.add(
        Portrait(
            user_id=user.id,
            kind=PortraitHorizon.RECENT_7D.value,
            strengths=[],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=now,
        )
    )
    if score is not None:
        db.add(
            Reputation(
                user_id=user.id,
                score=score,
                eligibility=Eligibility.ACTIVE.value,
            )
        )
    db.flush()
    return user


def test_ensure_default_opens_at_sixty_five(db: Session) -> None:
    user = _user(db, name="Alice")
    ReputationService().ensure_default(db, user.id)
    row = db.get(Reputation, user.id)
    assert row is not None
    assert row.score == REPUTATION_INITIAL_SCORE == 65


def test_default_two_poor_chances(db: Session) -> None:
    reputation = ReputationService()
    alice = _user(db, name="Alice")
    reputation.ensure_default(db, alice.id)
    match = MatchService(db, reputation=reputation)
    now = datetime.now(UTC)

    reputation.apply_poor(db, alice.id)
    assert db.get(Reputation, alice.id).score == REPUTATION_MIN_ACTIVE_SCORE
    assert reputation.allows_match(db, alice.id, now)
    waiting = match.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    assert waiting.status == MatchConditionStatus.WAITING
    match.cancel(alice)

    reputation.apply_poor(db, alice.id)
    assert db.get(Reputation, alice.id).score == (
        REPUTATION_MIN_ACTIVE_SCORE - REPUTATION_POOR_DELTA
    )
    assert not reputation.allows_match(db, alice.id, now)
    with pytest.raises(BizException) as exc:
        match.submit(alice, want_text="还想学理财", want_tag=StrengthTag.FINANCE)
    assert exc.value.code == BizCode.CONFLICT


def test_initial_sixty_one_one_poor_locks(db: Session) -> None:
    settings = AppSettings(
        reputation_initial_score=61,
        reputation_poor_delta=REPUTATION_POOR_DELTA,
        reputation_min_active_score=REPUTATION_MIN_ACTIVE_SCORE,
        reputation_good_delta=REPUTATION_GOOD_DELTA,
        reputation_score_max=REPUTATION_SCORE_MAX,
    )
    reputation = ReputationService(settings=settings)
    alice = _user(db, name="Alice")
    reputation.ensure_default(db, alice.id)
    assert db.get(Reputation, alice.id).score == 61
    reputation.apply_poor(db, alice.id)
    assert db.get(Reputation, alice.id).score == 61 - REPUTATION_POOR_DELTA
    assert not reputation.allows_match(db, alice.id, datetime.now(UTC))
    with pytest.raises(BizException) as exc:
        MatchService(db, reputation=reputation).submit(
            alice, want_text="想学健身", want_tag=StrengthTag.FITNESS
        )
    assert exc.value.code == BizCode.CONFLICT


def test_good_adds_until_max(db: Session) -> None:
    reputation = ReputationService()
    alice = _user(db, name="Alice", score=REPUTATION_INITIAL_SCORE)
    reputation.apply_good(db, alice.id)
    assert db.get(Reputation, alice.id).score == REPUTATION_INITIAL_SCORE + REPUTATION_GOOD_DELTA
    row = db.get(Reputation, alice.id)
    assert row is not None
    row.score = REPUTATION_SCORE_MAX
    db.flush()
    reputation.apply_good(db, alice.id)
    assert db.get(Reputation, alice.id).score == REPUTATION_SCORE_MAX


def test_poor_does_not_go_below_zero(db: Session) -> None:
    reputation = ReputationService()
    alice = _user(db, name="Alice", score=0)
    reputation.apply_poor(db, alice.id)
    assert db.get(Reputation, alice.id).score == 0


def test_get_view_includes_gauge_bounds(db: Session) -> None:
    alice = _user(db, name="Alice")
    view = ReputationService().get_view(db, alice.id)
    assert view.score == REPUTATION_INITIAL_SCORE
    assert view.score_max == REPUTATION_SCORE_MAX
    assert view.min_active_score == REPUTATION_MIN_ACTIVE_SCORE
    assert view.eligibility == Eligibility.ACTIVE


def test_me_reputation_via_http(db: Session) -> None:
    alice = _user(db, name="Alice")
    ReputationService().ensure_default(db, alice.id)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(reputation_router)
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_reputation_service] = lambda: ReputationService()
    app.dependency_overrides[get_current_user] = lambda: alice
    client = TestClient(app)
    response = client.get("/me/reputation")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["score"] == REPUTATION_INITIAL_SCORE
    assert body["data"]["score_max"] == REPUTATION_SCORE_MAX
    assert body["data"]["min_active_score"] == REPUTATION_MIN_ACTIVE_SCORE


def test_me_reputation_unauthorized(db: Session) -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(reputation_router)

    def deny() -> User:
        raise BizException("未登录", code=BizCode.UNAUTHORIZED)

    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_reputation_service] = lambda: ReputationService()
    app.dependency_overrides[get_current_user] = deny
    client = TestClient(app)
    response = client.get("/me/reputation")
    assert response.status_code == 200
    assert response.json()["code"] == 401
