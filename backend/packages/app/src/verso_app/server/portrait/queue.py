"""Redis 画像同步队列：去重入队，worker / 进程内 poller 消费。"""

from __future__ import annotations

from typing import Protocol

from verso_common.constants import PORTRAIT_SYNC_PENDING_TTL_SEC

QUEUE_KEY = "portrait:sync:queue"


class RedisQueueLike(Protocol):
    def set(
        self,
        name: str,
        value: str,
        ex: int | None = None,
        nx: bool = False,
    ) -> object: ...

    def delete(self, *names: str) -> object: ...

    def rpush(self, name: str, *values: str) -> object: ...

    def blpop(self, keys: list[str] | str, timeout: int = 0) -> tuple[str, str] | None: ...


class PortraitSyncQueue:
    def __init__(
        self,
        redis: RedisQueueLike,
        *,
        pending_ttl_sec: int = PORTRAIT_SYNC_PENDING_TTL_SEC,
    ) -> None:
        self._redis = redis
        self._pending_ttl_sec = max(pending_ttl_sec, 60)

    def enqueue(self, user_id: str) -> bool:
        """去重入队。已在 pending 中则返回 False。"""
        pending = _pending_key(user_id)
        placed = self._redis.set(pending, "1", ex=self._pending_ttl_sec, nx=True)
        if not placed:
            return False
        self._redis.rpush(QUEUE_KEY, user_id)
        return True

    def pop(self, *, timeout_sec: int = 5) -> str | None:
        item = self._redis.blpop(QUEUE_KEY, timeout=max(timeout_sec, 0))
        if item is None:
            return None
        _key, user_id = item
        return user_id

    def ack(self, user_id: str) -> None:
        self._redis.delete(_pending_key(user_id))


def _pending_key(user_id: str) -> str:
    return f"portrait:sync:pending:{user_id}"
