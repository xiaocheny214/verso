"""身份、匹配、交换、评审、声望的对外视图。不含 ORM。"""

from datetime import datetime

from pydantic import BaseModel, Field

from verso_common.constants import (
    REPUTATION_INITIAL_SCORE,
    REPUTATION_MIN_ACTIVE_SCORE,
    REPUTATION_SCORE_MAX,
)
from verso_common.enums import (
    Eligibility,
    ExchangeStatus,
    MatchConditionStatus,
    PortraitHorizon,
    PortraitSource,
    ReviewVerdict,
    StrengthTag,
)


class Strength(BaseModel):
    tag: StrengthTag
    source: PortraitSource
    evidence_title: str | None = None
    evidence_url: str | None = None


class PortraitView(BaseModel):
    horizon: PortraitHorizon
    strengths: list[Strength] = Field(default_factory=list)


class UserCard(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None
    portraits: list[PortraitView] = Field(default_factory=list)


class ArticleArchiveView(BaseModel):
    id: str
    title: str
    source_url: str
    status: str
    error_class: str | None = None


class KnowledgeBaseView(BaseModel):
    id: str
    name: str
    embedding_model: str
    collection_name: str
    storage_profile_id: str | None = None


class FailedFetchListView(BaseModel):
    items: list[ArticleArchiveView] = Field(default_factory=list)
    capture_token: str = ""


class ArchiveQueueView(BaseModel):
    """工作台队列：未就绪正文 + 计数。capture_token 仅在仍有待补抓时下发。"""

    items: list[ArticleArchiveView] = Field(default_factory=list)
    capture_token: str = ""
    pending_count: int = 0
    failed_count: int = 0
    ready_count: int = 0


class MatchPeerView(BaseModel):
    id: str
    name: str
    avatar_url: str | None = None
    want_text: str
    want_tag: StrengthTag
    strengths: list[StrengthTag] = Field(default_factory=list)
    score: int


class MatchConditionView(BaseModel):
    id: str
    want_text: str
    want_tag: StrengthTag
    status: MatchConditionStatus
    pair_id: str | None = None
    waiting_until: datetime | None = None
    pair_closes_at: datetime | None = None
    peer: MatchPeerView | None = None


class PairView(BaseModel):
    """配上之后给会话列表看的对方名片。"""

    exchange_id: str
    peer_id: str
    peer_name: str
    peer_avatar_url: str | None = None
    peer_strengths: list[StrengthTag] = Field(default_factory=list)
    peer_want_text: str


class ExchangeView(BaseModel):
    id: str
    user_a_id: str
    user_b_id: str
    status: ExchangeStatus
    opened_at: datetime
    closes_at: datetime
    closed_at: datetime | None = None


class MessageView(BaseModel):
    id: str
    exchange_id: str
    sender_id: str
    text: str
    created_at: datetime


class ReviewView(BaseModel):
    id: str
    exchange_id: str
    reviewer_id: str
    reviewee_id: str
    verdict: ReviewVerdict
    score: int | None = None
    reason: str = ""


class ReputationView(BaseModel):
    score: int = REPUTATION_INITIAL_SCORE
    score_max: int = REPUTATION_SCORE_MAX
    min_active_score: int = REPUTATION_MIN_ACTIVE_SCORE
    eligibility: Eligibility = Eligibility.ACTIVE
    suspended_until: datetime | None = None
