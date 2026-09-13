"""match：当次求知条件状态。配上之后关系交给 exchange。"""

from enum import StrEnum


class MatchConditionStatus(StrEnum):
    WAITING = "waiting"
    MATCHED = "matched"
    CANCELLED = "cancelled"
