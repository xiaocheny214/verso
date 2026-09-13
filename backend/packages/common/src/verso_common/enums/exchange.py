"""exchange：一对关系及其下的留言。"""

from enum import StrEnum


class ExchangeStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
