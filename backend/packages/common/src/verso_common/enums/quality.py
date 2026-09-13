"""quality：不满意之后的 AI 裁决。"""

from enum import StrEnum


class ReviewVerdict(StrEnum):
    """人先点不满意，模型只回答是不是真的差。"""

    POOR = "poor"
    GOOD = "good"
    UNCLEAR = "unclear"
