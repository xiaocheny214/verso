"""RocketMQ 生产者。import 不连代理；第一次 ``publish`` 才 startup。"""

from __future__ import annotations

from typing import Protocol

from rocketmq import ClientConfiguration, Credentials, Message, Producer

from verso_common.ids import Snowflake
from verso_framework.config.rocketmq import RocketMqSettings, get_rocketmq_settings
from verso_framework.mq.event import DeliveryEvent


class MqSender(Protocol):
    def send(self, message: Message) -> object: ...


class RocketMqProducer:
    def __init__(
        self,
        settings: RocketMqSettings | None = None,
        *,
        sender: MqSender | None = None,
        snowflake: Snowflake | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_rocketmq_settings()
        self._sender = sender
        self._owned = sender is None
        self.snowflake = snowflake or Snowflake(self._settings.worker_id)

    def publish(self, event: DeliveryEvent) -> None:
        self._client().send(to_broker_message(event, topic=self._settings.topic))

    def shutdown(self) -> None:
        if self._owned and self._sender is not None:
            self._sender.shutdown()
            self._sender = None

    def _client(self) -> MqSender:
        if self._sender is None:
            producer = Producer(_configuration(self._settings), (self._settings.topic,))
            producer.startup()
            self._sender = producer
        return self._sender


def to_broker_message(event: DeliveryEvent, *, topic: str) -> Message:
    message = Message()
    message.topic = topic
    message.body = event.model_dump_json().encode("utf-8")
    message.tag = event.event_type.value
    message.keys = event.event_id
    return message


def _configuration(settings: RocketMqSettings) -> ClientConfiguration:
    return ClientConfiguration(
        settings.endpoints,
        Credentials(settings.access_key, settings.secret_key),
        request_timeout=settings.request_timeout_sec,
    )
