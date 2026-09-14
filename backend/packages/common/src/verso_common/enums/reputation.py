"""成色：匹配资格。只有这里改分。"""

from enum import StrEnum


class Eligibility(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
