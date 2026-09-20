"""match：当次求知条件状态。配上之后关系交给 exchange。"""

from enum import StrEnum


class MatchConditionStatus(StrEnum):
    WAITING = "waiting"
    MATCHED = "matched"
    CANCELLED = "cancelled"


class MatchEvaluationOutcome(StrEnum):
    """一次模型判断的结论。硬过滤没进模型的候选不记。"""

    PAIRED = "paired"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"
    SKIPPED_UNCLEAR = "skipped_unclear"
    SKIPPED_LOW_CONFIDENCE = "skipped_low_confidence"
    SKIPPED_ERROR = "skipped_error"
    SKIPPED_LOCK = "skipped_lock"
