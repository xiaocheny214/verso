"""归档文章状态。"""

from enum import StrEnum


class ArticleStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
