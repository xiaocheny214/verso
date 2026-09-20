"""Redis 上的登录 intent、session、知乎 token。"""

from __future__ import annotations

import secrets
from typing import Protocol


class RedisLike(Protocol):
    def set(self, name: str, value: str, ex: int | None = None) -> object: ...

    def get(self, name: str) -> str | None: ...

    def delete(self, *names: str) -> object: ...


class SessionStore:
    def __init__(self, redis: RedisLike) -> None:
        self._redis = redis

    def put_intent(self, ttl_sec: int) -> str:
        nonce = secrets.token_urlsafe(16)
        self._redis.set(f"oauth:intent:{nonce}", "1", ex=ttl_sec)
        return nonce

    def consume_intent(self, nonce: str) -> bool:
        key = f"oauth:intent:{nonce}"
        getter = getattr(self._redis, "getdel", None)
        if callable(getter):
            return bool(getter(key))
        if not self._redis.get(key):
            return False
        self._redis.delete(key)
        return True

    def save_grant(self, user_id: str, access_token: str, ttl_sec: int) -> None:
        self._redis.set(f"oauth:zhihu:{user_id}", access_token, ex=max(ttl_sec, 60))

    def load_grant(self, user_id: str) -> str | None:
        return self._redis.get(f"oauth:zhihu:{user_id}")

    def put_capture_token(self, user_id: str, ttl_sec: int = 600) -> str:
        token = secrets.token_urlsafe(24)
        self._redis.set(f"article:capture:{token}", user_id, ex=max(ttl_sec, 60))
        return token

    def user_id_for_capture(self, token: str) -> str | None:
        if not token:
            return None
        return self._redis.get(f"article:capture:{token}")

    def issue_session(self, user_id: str, ttl_sec: int) -> str:
        old = self._redis.get(f"session:user:{user_id}")
        if old:
            self._redis.delete(f"session:{old}")
        sid = secrets.token_urlsafe(32)
        self._redis.set(f"session:{sid}", user_id, ex=ttl_sec)
        self._redis.set(f"session:user:{user_id}", sid, ex=ttl_sec)
        return sid

    def user_id_for(self, sid: str) -> str | None:
        return self._redis.get(f"session:{sid}")

    def drop_session(self, sid: str) -> None:
        user_id = self._redis.get(f"session:{sid}")
        self._redis.delete(f"session:{sid}")
        if user_id:
            current = self._redis.get(f"session:user:{user_id}")
            if current == sid:
                self._redis.delete(f"session:user:{user_id}")
