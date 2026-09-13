from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.server.identity.models import Portrait, User
from verso_app.server.match.models import MatchCondition
from verso_app.server.match.service import MatchService
from verso_app.server.reputation.models import Reputation
from verso_app.web.api.match import router as match_router
from verso_app.web.handler import register_exception_handlers
from verso_app.web.middleware.auth import get_current_user, get_match_service
from verso_common.constants import PAIR_WINDOW_HOURS, REPUTATION_INITIAL_SCORE
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
from verso_framework.db.base import Base


class FakeExchange:
    def __init__(self) -> None:
        self.opened: list[dict] = []

    def open(self, *, pair_id, user_a_id, user_b_id, closes_at) -> None:
        self.opened.append(
            {
                "pair_id": pair_id,
                "user_a_id": user_a_id,
                "user_b_id": user_b_id,
                "closes_at": closes_at,
            }
        )


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


def _user(
    db: Session,
    *,
    name: str,
    stable: list[StrengthTag],
    recent: list[StrengthTag] | None = None,
    eligibility: Eligibility = Eligibility.ACTIVE,
    score: int = REPUTATION_INITIAL_SCORE,
) -> User:
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
            strengths=[tag.value for tag in stable],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=now,
        )
    )
    db.add(
        Portrait(
            user_id=user.id,
            kind=PortraitHorizon.RECENT_7D.value,
            strengths=[tag.value for tag in (recent or [])],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            window_start=now - timedelta(days=7),
            window_end=now,
            synced_at=now,
        )
    )
    db.add(
        Reputation(
            user_id=user.id,
            score=score,
            eligibility=eligibility.value,
        )
    )
    db.flush()
    return user


def test_match_conditions_table_has_no_strengths(db: Session) -> None:
    columns = {column["name"] for column in inspect(db.get_bind()).get_columns("match_conditions")}
    assert "strengths" not in columns
    assert {"want_text", "want_tag", "status", "pair_id", "waiting_until", "pair_closes_at"} <= columns


def test_complementary_pair_shares_pair_id(db: Session) -> None:
    exchange = FakeExchange()
    service = MatchService(db, exchange=exchange)
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING, StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS, StrengthTag.TRAINING])
    waiting = service.submit(alice, want_text="徒手训练怎么入门", want_tag=StrengthTag.FITNESS)
    assert waiting.status == MatchConditionStatus.WAITING
    assert waiting.peer is None
    matched = service.submit(bob, want_text="互联网产品怎么做", want_tag=StrengthTag.INTERNET)
    assert matched.status == MatchConditionStatus.MATCHED
    assert matched.pair_id is not None
    assert matched.peer is not None
    assert matched.peer.id == str(alice.id)
    assert matched.peer.want_tag == StrengthTag.FITNESS
    assert StrengthTag.PROGRAMMING in matched.peer.strengths
    alice_view = service.current(alice)
    assert alice_view.pair_id == matched.pair_id
    assert alice_view.peer is not None
    assert alice_view.peer.id == str(bob.id)
    rows = db.scalars(select(MatchCondition)).all()
    assert {row.pair_id for row in rows} == {UUID(matched.pair_id)}
    assert "strengths" not in MatchCondition.__table__.c
    assert len(exchange.opened) == 1
    assert exchange.opened[0]["pair_id"] == UUID(matched.pair_id)
    assert matched.pair_closes_at is not None
    delta = matched.pair_closes_at - datetime.now(UTC)
    assert timedelta(hours=PAIR_WINDOW_HOURS - 1) < delta <= timedelta(hours=PAIR_WINDOW_HOURS)


def test_one_way_and_same_tag_stay_waiting(db: Session) -> None:
    service = MatchService(db)
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])
    carol = _user(db, name="Carol", stable=[StrengthTag.PROGRAMMING])
    first = service.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    second = service.submit(bob, want_text="也想学健身", want_tag=StrengthTag.FITNESS)
    assert first.status == MatchConditionStatus.WAITING
    assert second.status == MatchConditionStatus.WAITING
    third = service.submit(carol, want_text="想学编程", want_tag=StrengthTag.PROGRAMMING)
    assert third.status == MatchConditionStatus.WAITING
    dave = _user(db, name="Dave", stable=[StrengthTag.PROGRAMMING])
    same = service.submit(dave, want_text="也想学编程", want_tag=StrengthTag.PROGRAMMING)
    assert same.status == MatchConditionStatus.WAITING


def test_recent_strength_counts_in_covers(db: Session) -> None:
    service = MatchService(db)
    alice = _user(
        db,
        name="Alice",
        stable=[StrengthTag.PROGRAMMING],
        recent=[StrengthTag.FITNESS],
    )
    bob = _user(db, name="Bob", stable=[StrengthTag.INTERNET])
    service.submit(alice, want_text="想了解互联网", want_tag=StrengthTag.INTERNET)
    matched = service.submit(bob, want_text="徒手怎么练", want_tag=StrengthTag.FITNESS)
    assert matched.status == MatchConditionStatus.MATCHED
    assert matched.peer is not None
    assert StrengthTag.FITNESS in matched.peer.strengths


def test_duplicate_waiting_conflicts(db: Session) -> None:
    service = MatchService(db)
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING])
    service.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    with pytest.raises(BizException) as exc:
        service.submit(alice, want_text="还想学理财", want_tag=StrengthTag.FINANCE)
    assert exc.value.code == BizCode.CONFLICT


def test_suspended_user_cannot_enter(db: Session) -> None:
    service = MatchService(db)
    alice = _user(
        db,
        name="Alice",
        stable=[StrengthTag.PROGRAMMING],
        eligibility=Eligibility.SUSPENDED,
    )
    with pytest.raises(BizException) as exc:
        service.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    assert exc.value.code == BizCode.CONFLICT


def test_cancel_only_waiting(db: Session) -> None:
    service = MatchService(db)
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING, StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])
    service.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    cancelled = service.cancel(alice)
    assert cancelled.status == MatchConditionStatus.CANCELLED
    service.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    service.submit(bob, want_text="想学互联网", want_tag=StrengthTag.INTERNET)
    with pytest.raises(BizException) as exc:
        service.cancel(alice)
    assert exc.value.code == BizCode.CONFLICT


def test_waiting_expires(db: Session) -> None:
    service = MatchService(db)
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING])
    view = service.submit(alice, want_text="想学健身", want_tag=StrengthTag.FITNESS)
    row = db.get(MatchCondition, UUID(view.id))
    assert row is not None
    row.waiting_until = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert service.expire_waiting() == 1
    with pytest.raises(BizException) as exc:
        service.current(alice)
    assert exc.value.code == BizCode.NOT_FOUND


def test_submit_via_http(db: Session) -> None:
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING])
    service = MatchService(db)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(match_router)
    app.dependency_overrides[get_match_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: alice
    client = TestClient(app)
    response = client.post(
        "/match/conditions",
        json={"want_text": "徒手训练怎么入门", "want_tag": "健身"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["status"] == "waiting"
    assert body["data"]["want_tag"] == "健身"
    assert "strengths" not in body["data"]
    me = client.get("/match/conditions/me")
    assert me.json()["data"]["id"] == body["data"]["id"]
