"""大模型调用失败分类。供 quality 裁决与内部重试决策，不直接展示给用户。"""

from enum import StrEnum


class ModelErrorType(StrEnum):
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    NETWORK = "network"
    AUTH = "auth"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"

    @property
    def retryable(self) -> bool:
        return self in {
            ModelErrorType.RATE_LIMIT,
            ModelErrorType.TIMEOUT,
            ModelErrorType.NETWORK,
        }
