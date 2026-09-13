"""身份、匹配、交换、评审、声望的对外视图。不含 ORM。"""

from datetime import datetime

from pydantic import BaseModel, Field

from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import (
    Eligibility,
    ExchangeStatus,
    PortraitHorizon,
    PortraitSource,
    ReviewVerdict,
    StrengthTag,
    TicketStatus,
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


class TicketView(BaseModel):
    id: str
    want_text: str
    want_tag: StrengthTag | None = None
    status: TicketStatus


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


class ReputationView(BaseModel):
    score: int = REPUTATION_INITIAL_SCORE
    eligibility: Eligibility = Eligibility.ACTIVE
    suspended_until: datetime | None = None
