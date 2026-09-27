import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_common.ids import Snowflake
from verso_framework.db.base import Base
from verso_framework.mq import (
    OutboxMessage,
    OutboxService,
    new_knowledge_process_event,
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


class DummySender:
    def __init__(self, fail_first: bool = False) -> None:
        self.sent: list[object] = []
        self.fail_first = fail_first
        self.call_count = 0

    def send(self, message: object) -> None:
        self.call_count += 1
        if self.fail_first and self.call_count == 1:
            raise RuntimeError("broker temporary unavailable")
        self.sent.append(message)


def test_outbox_save_and_publish_success(db: Session) -> None:
    from verso_framework.mq.producer import RocketMqProducer

    snowflake = Snowflake(1)
    event = new_knowledge_process_event(
        snowflake,
        user_id=str(uuid.uuid4()),
        knowledge_base_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
    )
    row = OutboxService.save_event(db, event)
    assert row.status == "pending"
    db.commit()

    sender = DummySender()
    producer = RocketMqProducer(sender=sender, snowflake=snowflake)
    ok = OutboxService.publish_event(db, producer=producer, event=event)
    assert ok is True
    assert len(sender.sent) == 1

    saved = db.get(OutboxMessage, event.event_id)
    assert saved is not None
    assert saved.status == "published"
    assert saved.published_at is not None


def test_outbox_publish_failure_retains_pending_and_relays(db: Session) -> None:
    from verso_framework.mq.producer import RocketMqProducer

    snowflake = Snowflake(1)
    event = new_knowledge_process_event(
        snowflake,
        user_id=str(uuid.uuid4()),
        knowledge_base_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
    )
    OutboxService.save_event(db, event)
    db.commit()

    sender = DummySender(fail_first=True)
    producer = RocketMqProducer(sender=sender, snowflake=snowflake)

    # 直发失败
    ok = OutboxService.publish_event(db, producer=producer, event=event)
    assert ok is False
    saved = db.get(OutboxMessage, event.event_id)
    assert saved is not None
    assert saved.status == "pending"
    assert saved.retry_count == 1
    assert "broker temporary unavailable" in (saved.last_error or "")

    # 后台 relay 补偿发送
    relayed = OutboxService.relay_pending(db, producer=producer, limit=10)
    assert relayed == 1
    saved_after = db.get(OutboxMessage, event.event_id)
    assert saved_after is not None
    assert saved_after.status == "published"
    assert saved_after.published_at is not None
