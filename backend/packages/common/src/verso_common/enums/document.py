"""知识库文档处理状态。"""

from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
