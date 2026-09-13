"""match：当次求知表单（Ticket）状态。配上之后关系交给 exchange。"""

from enum import StrEnum


class TicketStatus(StrEnum):
    OPEN = "open"
    MATCHED = "matched"
    CANCELLED = "cancelled"
