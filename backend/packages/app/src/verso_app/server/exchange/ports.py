"""exchange 开对端口。match 配上后调用；消息表不在本 feat。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol


class ExchangeOpener(Protocol):
    def open(
        self,
        *,
        pair_id: uuid.UUID,
        user_a_id: uuid.UUID,
        user_b_id: uuid.UUID,
        closes_at: datetime,
    ) -> None: ...


class NoopExchangeOpener:
    def open(
        self,
        *,
        pair_id: uuid.UUID,
        user_a_id: uuid.UUID,
        user_b_id: uuid.UUID,
        closes_at: datetime,
    ) -> None:
        return
