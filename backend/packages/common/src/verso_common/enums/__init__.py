"""共享枚举。"""

from verso_common.enums.article import ArticleStatus
from verso_common.enums.auth import UserStatus
from verso_common.enums.biz_code import BizCode
from verso_common.enums.chunk import ChunkStrategy
from verso_common.enums.document import DocumentStatus
from verso_common.enums.exchange import ExchangeStatus
from verso_common.enums.match import MatchConditionStatus, MatchEvaluationOutcome
from verso_common.enums.model import ModelErrorType
from verso_common.enums.portrait import PortraitHorizon, PortraitSource, StrengthTag
from verso_common.enums.quality import ReviewVerdict
from verso_common.enums.realtime import RealtimeChannel
from verso_common.enums.reputation import Eligibility

__all__ = [
    "ArticleStatus",
    "BizCode",
    "ChunkStrategy",
    "DocumentStatus",
    "Eligibility",
    "ExchangeStatus",
    "MatchConditionStatus",
    "MatchEvaluationOutcome",
    "ModelErrorType",
    "PortraitHorizon",
    "PortraitSource",
    "RealtimeChannel",
    "ReviewVerdict",
    "StrengthTag",
    "UserStatus",
]
