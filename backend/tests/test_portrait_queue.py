from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fakes import FakeRedis, FakeZhihu
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.server.auth.models import User  # noqa: F401
from verso_app.server.auth.session_store import SessionStore
from verso_app.server.portrait.models import Portrait
from verso_app.server.portrait.queue import QUEUE_KEY, PortraitSyncQueue
from verso_app.server.portrait.service import PortraitService
from verso_common.constants import PORTRAIT_SYNC_STALE_DAYS
from verso_common.enums import PortraitHorizon, PortraitSource
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


def test_queue_dedupes_pending(db: Session) -> None:
    redis = FakeRedis()
    queue = PortraitSyncQueue(redis)
    user_id = str(uuid4())
    assert queue.enqueue(user_id) is True
    assert queue.enqueue(user_id) is False
    assert redis.lists[QUEUE_KEY] == [user_id]


def test_needs_sync_when_no_stable_row(db: Session) -> None:
    redis = FakeRedis()
    service = PortraitService(
        session=db,
        grants=SessionStore(redis),
        zhihu=FakeZhihu(),
        queue=PortraitSyncQueue(redis),
    )
    assert service.needs_sync(uuid4()) is True


def test_needs_sync_false_when_fresh(db: Session) -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    db.add(
        Portrait(
            user_id=user_id,
            kind=PortraitHorizon.STABLE.value,
            strengths=[],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=now,
        )
    )
    db.flush()
    redis = FakeRedis()
    service = PortraitService(
        session=db,
        grants=SessionStore(redis),
        zhihu=FakeZhihu(),
        queue=PortraitSyncQueue(redis),
    )
    assert service.needs_sync(user_id) is False


def test_needs_sync_true_when_stale(db: Session) -> None:
    user_id = uuid4()
    old = datetime.now(UTC) - timedelta(days=PORTRAIT_SYNC_STALE_DAYS + 1)
    db.add(
        Portrait(
            user_id=user_id,
            kind=PortraitHorizon.STABLE.value,
            strengths=[],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=old,
        )
    )
    db.flush()
    redis = FakeRedis()
    service = PortraitService(
        session=db,
        grants=SessionStore(redis),
        zhihu=FakeZhihu(),
        queue=PortraitSyncQueue(redis),
    )
    assert service.needs_sync(user_id) is True


def test_enqueue_if_stale_skips_fresh(db: Session) -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    db.add(
        Portrait(
            user_id=user_id,
            kind=PortraitHorizon.STABLE.value,
            strengths=[],
            source=PortraitSource.CONTENTS.value,
            evidence=[],
            synced_at=now,
        )
    )
    db.flush()
    redis = FakeRedis()
    queue = PortraitSyncQueue(redis)
    service = PortraitService(
        session=db,
        grants=SessionStore(redis),
        zhihu=FakeZhihu(),
        queue=queue,
    )
    assert service.enqueue_if_stale(user_id) is False
    assert QUEUE_KEY not in redis.lists


class _BlpopTimeoutRedis(FakeRedis):
    def blpop(self, keys: list[str] | str, timeout: int = 0) -> tuple[str, str] | None:
        raise TimeoutError("Timeout reading from socket")


def test_pop_treats_blpop_read_timeout_as_empty() -> None:
    queue = PortraitSyncQueue(_BlpopTimeoutRedis())
    assert queue.pop(timeout_sec=5) is None
