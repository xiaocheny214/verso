"""意图节点分层与类型。"""

from enum import StrEnum


class IntentLayer(StrEnum):
    DOMAIN = "domain"
    TOPIC = "topic"
    OTHER = "other"


class IntentKind(StrEnum):
    KB_RETRIEVE = "kb_retrieve"
