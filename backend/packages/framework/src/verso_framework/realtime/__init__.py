from typing import Any, Protocol

from verso_common.enums import RealtimeChannel


class RealtimeBus(Protocol):
    """按频道扇出。匹配通知走 user，对话事件走 exchange。禁止全站广播。"""

    async def subscribe(self, channel: RealtimeChannel, key: str, connection_id: str) -> None: ...

    async def unsubscribe(self, channel: RealtimeChannel, key: str, connection_id: str) -> None: ...

    async def publish(self, channel: RealtimeChannel, key: str, event: str, payload: dict[str, Any]) -> None: ...
