from pydantic import BaseModel

from verso_common.enums import ArticleSource, InviteStatus, MatchRole


class UserPreferences(BaseModel):
    summary_generate: bool = True
    summary_auto_save: bool = False


class ArticleCard(BaseModel):
    id: str
    title: str
    excerpt: str
    url: str
    source: ArticleSource
    author_invitable: bool
    presence_count: int = 0
    cold_start: bool = False


class InviteView(BaseModel):
    id: str
    article_id: str
    from_user_id: str
    to_user_id: str
    status: InviteStatus
    room_id: str | None = None


class MatchCard(BaseModel):
    id: str
    article_title: str
    article_url: str
    opponent_name: str
    role: MatchRole
    duration_sec: int
    summary_text: str | None = None
