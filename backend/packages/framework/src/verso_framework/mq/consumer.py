"""RocketMQ 消费者。处理成功后才 ack；处理失败留着重投。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from rocketmq import FilterExpression, SimpleConsumer

from verso_framework.config.rocketmq import RocketMqSettings, get_rocketmq_settings
from verso_framework.mq.event import DeliveryEvent, parse_delivery_event
from verso_framework.mq.producer import _configuration


class MqReceiver(Protocol):
    def receive(self, max_message_num: int, invisible_duration: int) -> list[MqMessage] | None: ...

    def ack(self, message: MqMessage) -> None: ...


class MqMessage(Protocol):
    body: bytes


class RocketMqConsumer:
    def __init__(
        self,
        settings: RocketMqSettings | None = None,
        *,
        receiver: MqReceiver | None = None,
    ) -> None:
        self._settings = settings if settings is not None else get_rocketmq_settings()
        self._receiver = receiver
        self._owned = receiver is None

    def poll(self, handler: Callable[[DeliveryEvent], None]) -> int:
        """拉一批。返回成功 ack 的条数。某条处理失败时停在该条，已成功的仍 ack。"""
        receiver = self._client()
        batch = receiver.receive(
            self._settings.max_message_num,
            self._settings.invisible_duration_sec,
        )
        if not batch:
            return 0
        acked = 0
        for message in batch:
            handler(parse_delivery_event(message.body))
            receiver.ack(message)
            acked += 1
        return acked

    def shutdown(self) -> None:
        if self._owned and self._receiver is not None:
            self._receiver.shutdown()
            self._receiver = None

    def _client(self) -> MqReceiver:
        if self._receiver is None:
            consumer = SimpleConsumer(
                _configuration(self._settings),
                self._settings.consumer_group,
                await_duration=self._settings.await_duration_sec,
            )
            consumer.startup()
            consumer.subscribe(self._settings.topic, FilterExpression("*"))
            self._receiver = consumer
        return self._receiver
