"""identity：擅长闭集、画像来源与时间窗。"""

from enum import StrEnum


class StrengthTag(StrEnum):
    """擅长 / 本次想学的闭集标签。匹配只在这个集合里做双向覆盖。"""

    PROGRAMMING = "编程"
    INTERNET = "互联网"
    FITNESS = "健身"
    TRAINING = "运动训练"
    CAREER = "职场"
    STUDY = "学业"
    FINANCE = "理财"
    WRITING = "写作"
    DESIGN = "设计"
    HEALTH = "医学健康"
    LAW = "法律"
    OTHER = "其他"


class PortraitSource(StrEnum):
    """擅长从哪来。有创作证据时以创作为准，空号才允许自报。"""

    CONTENTS = "contents"
    SELF_REPORTED = "self_reported"


class PortraitHorizon(StrEnum):
    """画像时间窗：长期稳定 vs 近 7 天。"""

    STABLE = "stable"
    RECENT_7D = "recent_7d"


class UserStatus(StrEnum):
    ACTIVE = "active"
    BANNED = "banned"
    DELETED = "deleted"
