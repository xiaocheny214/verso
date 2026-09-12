from typing import Any, Protocol


class MqPublisher(Protocol):
    """server 只依赖这个端口。本期 Redis Stream / 进程内；以后换 RocketMQ 改实现。"""

    async def publish(self, topic: str, payload: dict[str, Any], *, delay_sec: int = 0) -> None: ...


class MqConsumer(Protocol):
    async def consume(self, topic: str) -> None: ...
