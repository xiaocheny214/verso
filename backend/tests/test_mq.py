import os
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from verso_common.ids import Snowflake
from verso_framework.config.rocketmq import RocketMqSettings
from verso_framework.mq import (
    JobEventType,
    RocketMqConsumer,
    RocketMqProducer,
    new_knowledge_process_event,
    new_portrait_sync_event,
    parse_delivery_event,
)
from verso_framework.mq.event import DeliveryEvent


class _Sent:
    def __init__(self) -> None:
        self.messages: list[object] = []

    def send(self, message: object) -> None:
        self.messages.append(message)


class _Raw:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.acked = False


class _Inbox:
    def __init__(self, messages: list[_Raw]) -> None:
        self._messages = messages
        self.acked: list[_Raw] = []

    def receive(self, max_message_num: int, invisible_duration: int) -> list[_Raw]:
        assert max_message_num == 16
        assert invisible_duration == 30
        return self._messages

    def ack(self, message: _Raw) -> None:
        message.acked = True
        self.acked.append(message)


def test_rocketmq_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("ROCKETMQ_"):
            monkeypatch.delenv(key, raising=False)
    settings = RocketMqSettings(_env_file=None)
    assert settings.endpoints == "localhost:8081"
    assert settings.topic == "verso-job"
    assert settings.consumer_group == "verso-worker"
    assert settings.worker_id == 1


def test_publish_uses_snowflake_event_id_and_tag() -> None:
    settings = RocketMqSettings(_env_file=None, worker_id=3)
    sender = _Sent()
    producer = RocketMqProducer(settings, sender=sender, snowflake=Snowflake(3))
    event = new_knowledge_process_event(
        producer.snowflake,
        user_id="user-1",
        knowledge_base_id="kb-1",
        document_id="doc-1",
        run_id="run-1",
        occurred_at=datetime(2026, 9, 25, tzinfo=UTC),
    )
    producer.publish(event)
    message = sender.messages[0]
    parsed = parse_delivery_event(message.body)
    assert parsed.event_id == event.event_id
    assert parsed.event_id.isdigit()
    assert message.tag == JobEventType.KNOWLEDGE_DOCUMENT_PROCESS
    assert event.event_id in message.keys
    assert message.topic == "verso-job"
    assert parsed.payload.run_id == "run-1"


def test_portrait_event_round_trip() -> None:
    event = new_portrait_sync_event(Snowflake(1), user_id="user-9")
    parsed = parse_delivery_event(event.model_dump_json())
    assert parsed.event_type == JobEventType.PORTRAIT_SYNC
    assert parsed.schema_version == 1
    assert parsed.payload.user_id == "user-9"
    assert parsed.aggregate_id == "user-9"


def test_unknown_schema_version_rejected() -> None:
    event = new_portrait_sync_event(Snowflake(1), user_id="user-9")
    raw = event.model_dump(mode="json")
    raw["schema_version"] = 2
    with pytest.raises(ValidationError):
        DeliveryEvent.model_validate(raw)


def test_consumer_acks_only_after_handler_succeeds() -> None:
    event = new_portrait_sync_event(Snowflake(1), user_id="user-9")
    ok = _Raw(event.model_dump_json().encode())
    bad = _Raw(b"{}")
    inbox = _Inbox([ok, bad])
    seen: list[str] = []

    def handle(item: DeliveryEvent) -> None:
        seen.append(item.event_id)

    consumer = RocketMqConsumer(RocketMqSettings(_env_file=None), receiver=inbox)
    with pytest.raises(ValidationError):
        consumer.poll(handle)
    assert seen == [event.event_id]
    assert ok.acked is True
    assert bad.acked is False
