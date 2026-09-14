from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from verso_app.server.auth.models import User
from verso_app.server.exchange.models import Exchange, Message
from verso_app.server.exchange.service import ExchangeService
from verso_app.server.match.service import MatchService
from verso_app.server.portrait.models import Portrait
from verso_app.server.reputation.models import Reputation
from verso_app.web.api.exchange import router as exchange_router
from verso_app.web.handler import register_exception_handlers
from verso_app.web.middleware.auth import get_current_user, get_exchange_service
from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import (
    BizCode,
    Eligibility,
    ExchangeStatus,
    PortraitHorizon,
    PortraitSource,
    StrengthTag,
    UserStatus,
)
from verso_common.exceptions import BizException
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


def _user(
    db: Session,
    *,
    name: str,
    stable: list[StrengthTag],
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


def test_match_open_writes_exchange_not_second_pair_table(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    row = db.get(Exchange, pair_id)
    assert row is not None
    assert {row.user_a_id, row.user_b_id} == {alice.id, bob.id}
    assert row.status == ExchangeStatus.OPEN
    assert db.scalars(select(Message).where(Message.exchange_id == pair_id)).all() == []


def test_members_can_send_and_read_roundtrips(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    service = ExchangeService(db)
    first = service.send(alice, pair_id, text="深蹲一周三次")
    second = service.send(bob, pair_id, text="先做小需求")
    messages = service.list_messages(alice, pair_id)
    assert [item.text for item in messages] == ["深蹲一周三次", "先做小需求"]
    assert first.sender_id == str(alice.id)
    assert second.sender_id == str(bob.id)
    cards = service.list_mine(alice)
    assert len(cards) == 1
    assert cards[0].exchange_id == str(pair_id)
    assert cards[0].peer_id == str(bob.id)
    assert cards[0].peer_want_text == "互联网产品怎么做"
    assert StrengthTag.FITNESS in cards[0].peer_strengths


def test_outsider_cannot_see_pair(db: Session) -> None:
    _alice, _bob, pair_id = _pair(db)
    carol = _user(db, name="Carol", stable=[StrengthTag.WRITING])
    service = ExchangeService(db)
    with pytest.raises(BizException) as exc:
        service.list_messages(carol, pair_id)
    assert exc.value.code == BizCode.NOT_FOUND
    with pytest.raises(BizException) as send_exc:
        service.send(carol, pair_id, text="路过")
    assert send_exc.value.code == BizCode.NOT_FOUND


def test_close_stops_new_messages(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    service = ExchangeService(db)
    closed = service.close(alice, pair_id)
    assert closed.status == ExchangeStatus.CLOSED
    with pytest.raises(BizException) as exc:
        service.send(bob, pair_id, text="还想问一句")
    assert exc.value.code == BizCode.CONFLICT
    leftover = service.list_messages(bob, pair_id)
    assert leftover == []


def test_window_expiry_closes_pair(db: Session) -> None:
    alice, bob, pair_id = _pair(db)
    row = db.get(Exchange, pair_id)
    assert row is not None
    row.closes_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    service = ExchangeService(db)
    assert service.expire_open() == 1
    with pytest.raises(BizException) as exc:
        service.send(alice, pair_id, text="迟到")
    assert exc.value.code == BizCode.CONFLICT


def test_send_via_http(db: Session) -> None:
    alice, _bob, pair_id = _pair(db)
    service = ExchangeService(db)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(exchange_router)
    app.dependency_overrides[get_exchange_service] = lambda: service
    app.dependency_overrides[get_current_user] = lambda: alice
    client = TestClient(app)
    response = client.post(
        f"/exchanges/{pair_id}/messages",
        json={"text": "先练徒手蹲"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["text"] == "先练徒手蹲"
    listed = client.get(f"/exchanges/{pair_id}/messages")
    assert listed.json()["total"] == 1
    mine = client.get("/exchanges/me")
    assert mine.json()["total"] == 1
    assert mine.json()["data"][0]["peer_want_text"] == "互联网产品怎么做"
