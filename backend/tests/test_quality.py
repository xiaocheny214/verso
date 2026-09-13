from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from verso_app.server.exchange.service import ExchangeService
from verso_app.server.identity.models import Portrait, User
from verso_app.server.match.service import MatchService
from verso_app.server.quality.judge import LlmAnswerJudge, parse_verdict
from verso_app.server.quality.models import Review
from verso_app.server.quality.service import QualityService
from verso_app.server.reputation.models import Reputation
from verso_app.server.reputation.service import ReputationService
from verso_app.web.api.quality import router as quality_router
from verso_app.web.handler import register_exception_handlers
from verso_app.web.middleware.auth import get_current_user, get_quality_service
from verso_common.constants import REPUTATION_INITIAL_SCORE, REPUTATION_POOR_DELTA
from verso_common.enums import (
    BizCode,
    Eligibility,
    PortraitHorizon,
    PortraitSource,
    ReviewVerdict,
    StrengthTag,
    UserStatus,
)
from verso_common.exceptions import BizException
from verso_framework.db.base import Base


class FixedJudge:
    def __init__(self, verdict: ReviewVerdict) -> None:
        self.verdict = verdict

    def judge(self, *, want_text: str, answer: str) -> ReviewVerdict:
        return self.verdict


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


def _user(db: Session, *, name: str, stable: list[StrengthTag]) -> User:
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
            strengths=[],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=now,
        )
    )
    db.add(
        Reputation(
            user_id=user.id,
            score=REPUTATION_INITIAL_SCORE,
            eligibility=Eligibility.ACTIVE.value,
        )
    )
    db.flush()
    return user


def _pair(db: Session) -> tuple[User, User, UUID]:
    alice = _user(db, name="Alice", stable=[StrengthTag.PROGRAMMING, StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])
    exchange = ExchangeService(db)
    match = MatchService(db, exchange=exchange)
    match.submit(alice, want_text="徒手训练怎么入门", want_tag=StrengthTag.FITNESS)
    view = match.submit(bob, want_text="互联网产品怎么做", want_tag=StrengthTag.INTERNET)
    assert view.pair_id is not None
    return alice, bob, UUID(view.pair_id)


def _quality(db: Session, verdict: ReviewVerdict) -> QualityService:
    return QualityService(
        db,
        exchange=ExchangeService(db),
        reputation=ReputationService(),
        judge=FixedJudge(verdict),
    )


def test_no_review_leaves_score(db: Session) -> None:
    _alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="先练徒手蹲")
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE
    assert db.scalars(select(Review)).all() == []


def test_poor_deducts_once(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="嗯")
    view = _quality(db, ReviewVerdict.POOR).submit(alice, pair_id)
    assert view.verdict == ReviewVerdict.POOR
    assert view.reviewee_id == str(bob.id)
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE - REPUTATION_POOR_DELTA
    assert db.get(Reputation, alice.id).score == REPUTATION_INITIAL_SCORE
    row = db.scalars(select(Review)).one()
    assert row.want_text == "徒手训练怎么入门"
    assert row.answer_text == "嗯"


@pytest.mark.parametrize("verdict", [ReviewVerdict.GOOD, ReviewVerdict.UNCLEAR])
def test_non_poor_does_not_deduct(db: Session, verdict: ReviewVerdict) -> None:
    alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="深蹲一周三次，先把动作做标准")
    _quality(db, verdict).submit(alice, pair_id)
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE


def test_no_answer_rejects_without_review(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    with pytest.raises(BizException) as exc:
        _quality(db, ReviewVerdict.POOR).submit(alice, pair_id)
    assert exc.value.code == BizCode.CONFLICT
    assert db.scalars(select(Review)).all() == []
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE


def test_duplicate_review_conflicts(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="先练徒手蹲")
    service = _quality(db, ReviewVerdict.POOR)
    service.submit(alice, pair_id)
    with pytest.raises(BizException) as exc:
        service.submit(alice, pair_id)
    assert exc.value.code == BizCode.CONFLICT
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE - REPUTATION_POOR_DELTA


def test_outsider_cannot_review(db: Session) -> None:
    _alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="先练徒手蹲")
    carol = _user(db, name="Carol", stable=[StrengthTag.WRITING])
    with pytest.raises(BizException) as exc:
        _quality(db, ReviewVerdict.POOR).submit(carol, pair_id)
    assert exc.value.code == BizCode.NOT_FOUND


def test_peers_can_review_each_other(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    exchange = ExchangeService(db)
    exchange.send(alice, pair_id, text="先做小需求")
    exchange.send(bob, pair_id, text="深蹲一周三次")
    _quality(db, ReviewVerdict.POOR).submit(alice, pair_id)
    _quality(db, ReviewVerdict.GOOD).submit(bob, pair_id)
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE - REPUTATION_POOR_DELTA
    assert db.get(Reputation, alice.id).score == REPUTATION_INITIAL_SCORE
    assert len(db.scalars(select(Review)).all()) == 2


def test_model_failure_records_unclear(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="先练徒手蹲")

    def boom(_prompt: str) -> str:
        raise RuntimeError("down")

    view = QualityService(
        db,
        exchange=ExchangeService(db),
        reputation=ReputationService(),
        judge=LlmAnswerJudge(boom),
    ).submit(alice, pair_id)
    assert view.verdict == ReviewVerdict.UNCLEAR
    assert db.get(Reputation, bob.id).score == REPUTATION_INITIAL_SCORE


def test_parse_verdict() -> None:
    assert parse_verdict("poor") == ReviewVerdict.POOR
    assert parse_verdict("GOOD\nthanks") == ReviewVerdict.GOOD
    assert parse_verdict("maybe") == ReviewVerdict.UNCLEAR
    assert parse_verdict("verdict: unclear") == ReviewVerdict.UNCLEAR


def test_create_review_via_http(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    ExchangeService(db).send(bob, pair_id, text="先练徒手蹲")
    service = _quality(db, ReviewVerdict.POOR)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(quality_router)
    app.dependency_overrides[get_quality_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: alice
    client = TestClient(app)
    response = client.post("/reviews", json={"exchange_id": str(pair_id)})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["verdict"] == "poor"
    assert body["data"]["reviewee_id"] == str(bob.id)
