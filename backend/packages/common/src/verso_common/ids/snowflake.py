"""Twitter Snowflake：41 位毫秒时间、10 位机器号、12 位序列。

同一进程内线程安全。多进程必须使用不同 ``worker_id``，否则可能撞号。
时钟回拨直接失败，不借用未来时间。
"""

from __future__ import annotations

import threading
import time

# 2026-01-01T00:00:00Z。时间差从这一刻起算，避免 id 过大。
EPOCH_MS = 1_767_225_600_000
WORKER_BITS = 10
SEQUENCE_BITS = 12
MAX_WORKER_ID = (1 << WORKER_BITS) - 1
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1
TIMESTAMP_SHIFT = WORKER_BITS + SEQUENCE_BITS
WORKER_SHIFT = SEQUENCE_BITS


class SnowflakeClockError(RuntimeError):
    """系统时钟回拨，拒绝发号。"""


class Snowflake:
    def __init__(self, worker_id: int, *, epoch_ms: int = EPOCH_MS) -> None:
        if not 0 <= worker_id <= MAX_WORKER_ID:
            raise ValueError(f"worker_id 必须在 0..{MAX_WORKER_ID}，收到 {worker_id}")
        self._worker_id = worker_id
        self._epoch_ms = epoch_ms
        self._lock = threading.Lock()
        self._last_ms = -1
        self._sequence = 0

    def next_id(self) -> int:
        with self._lock:
            now = _now_ms()
            if now < self._last_ms:
                raise SnowflakeClockError(f"时钟回拨 last_ms={self._last_ms} now_ms={now}")
            if now == self._last_ms:
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    now = _wait_next_ms(self._last_ms)
            else:
                self._sequence = 0
            self._last_ms = now
            delta = now - self._epoch_ms
            if delta < 0:
                raise SnowflakeClockError(f"当前时间早于纪元 epoch_ms={self._epoch_ms}")
            return (delta << TIMESTAMP_SHIFT) | (self._worker_id << WORKER_SHIFT) | self._sequence


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _wait_next_ms(last_ms: int) -> int:
    now = _now_ms()
    while now <= last_ms:
        now = _now_ms()
    return now
