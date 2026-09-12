from enum import StrEnum


class ArticleSource(StrEnum):
    ZHIHU_CONTENT = "zhihu_content"
    ZHIHU_SEARCH = "zhihu_search"


class InviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"


class RoomStatus(StrEnum):
    LIVE = "live"
    CLOSED = "closed"


class MatchRole(StrEnum):
    READER = "reader"
    AUTHOR = "author"
    CO_READER = "co_reader"


class RealtimeChannel(StrEnum):
    ARTICLE = "article"
    USER = "user"
    ROOM = "room"
