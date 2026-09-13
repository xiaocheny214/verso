"""知乎登录、画像采集、调用 reputation 开户。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_app.server.identity.models import Portrait, User
from verso_app.server.identity.session_store import SessionStore
from verso_app.server.identity.tagger import tags_from_text
from verso_app.server.reputation.service import ReputationService
from verso_common.constants import PORTRAIT_RECENT_DAYS
from verso_common.enums import BizCode, PortraitHorizon, PortraitSource, StrengthTag, UserStatus
from verso_common.exceptions import BizException
from verso_common.models import PortraitView, Strength, UserCard
from verso_framework.config.app import AppSettings
from verso_framework.providers.zhihu import (
    OAuthClient,
    UserDataClient,
    ZhihuCollection,
    ZhihuContent,
    ZhihuFollowee,
    ZhihuProfile,
)

logger = logging.getLogger("verso.identity")


@dataclass(frozen=True, slots=True)
class LoginStart:
    authorize_url: str
    nonce: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    user: User
    session_id: str


class IdentityService:
    def __init__(
        self,
        session: Session,
        store: SessionStore,
        oauth: OAuthClient,
        zhihu: UserDataClient,
        reputation: ReputationService,
        settings: AppSettings,
    ) -> None:
        self._session = session
        self._store = store
        self._oauth = oauth
        self._zhihu = zhihu
        self._reputation = reputation
        self._settings = settings

    def start_login(self) -> LoginStart:
        if not (
            self._settings.zhihu_client_id
            and self._settings.zhihu_client_secret
            and self._settings.zhihu_access_secret
            and self._settings.zhihu_redirect_uri
        ):
            raise BizException("未配置知乎登录", code=BizCode.INTERNAL_ERROR)
        nonce = self._store.put_intent(self._settings.oauth_intent_ttl_sec)
        return LoginStart(
            authorize_url=self._oauth.authorization_url(nonce),
            nonce=nonce,
        )

    def complete_login(self, *, code: str, nonce: str) -> LoginResult:
        if not code:
            raise BizException("缺少授权码", code=BizCode.BAD_REQUEST)
        if not nonce or not self._store.consume_intent(nonce):
            raise BizException("登录已过期，请重试", code=BizCode.BAD_REQUEST)
        try:
            token = self._oauth.exchange_code(code)
            profile = self._oauth.fetch_profile(token.access_token)
        except Exception:
            logger.exception("知乎换票或取名片失败")
            raise BizException("知乎授权失败", code=BizCode.BAD_REQUEST) from None
        user = self._upsert_user(profile)
        if user.status != UserStatus.ACTIVE:
            raise BizException("账号不可用", code=BizCode.FORBIDDEN)
        self._reputation.ensure_default(self._session, user.id)
        self._store.save_grant(str(user.id), token.access_token, token.expires_in)
        try:
            self.sync_portrait(user.id)
        except Exception:
            logger.exception("画像同步失败 user_id=%s", user.id)
        sid = self._store.issue_session(str(user.id), self._settings.session_ttl_sec)
        return LoginResult(user=user, session_id=sid)

    def logout(self, session_id: str) -> None:
        if session_id:
            self._store.drop_session(session_id)

    def require_user(self, session_id: str | None) -> User:
        if not session_id:
            raise BizException("未登录", code=BizCode.UNAUTHORIZED)
        raw_id = self._store.user_id_for(session_id)
        if not raw_id:
            raise BizException("未登录", code=BizCode.UNAUTHORIZED)
        user = self._session.get(User, uuid.UUID(raw_id))
        if user is None or user.status != UserStatus.ACTIVE:
            raise BizException("未登录", code=BizCode.UNAUTHORIZED)
        return user

    def get_card(self, user: User) -> UserCard:
        portraits = self._session.scalars(
            select(Portrait).where(Portrait.user_id == user.id)
        ).all()
        views = [_to_view(row) for row in portraits]
        views.sort(key=lambda item: item.horizon.value)
        return UserCard(
            id=str(user.id),
            name=user.display_name,
            avatar_url=user.avatar_url,
            portraits=views,
        )

    def sync_portrait(self, user_id: uuid.UUID) -> None:
        grant = self._store.load_grant(str(user_id))
        if not grant:
            raise BizException("授权已过期，请重新登录", code=BizCode.UNAUTHORIZED)
        contents = _safe_list("创作", lambda: self._zhihu.list_contents(grant))
        followees = _safe_list("关注", lambda: self._zhihu.list_followees(grant))
        favorites = _safe_list("收藏", lambda: self._zhihu.list_favorites(grant))
        now = datetime.now(UTC)
        recent_start = now - timedelta(days=PORTRAIT_RECENT_DAYS)
        stable_tags, stable_evidence, stable_source = _from_all(contents, followees, favorites)
        recent_tags, recent_evidence, recent_source = _from_recent(
            contents, favorites, recent_start
        )
        self._upsert_portrait(
            user_id,
            PortraitHorizon.STABLE,
            stable_tags,
            stable_evidence,
            source=stable_source,
            window_start=None,
            window_end=None,
            synced_at=now,
        )
        self._upsert_portrait(
            user_id,
            PortraitHorizon.RECENT_7D,
            recent_tags,
            recent_evidence,
            source=recent_source,
            window_start=recent_start,
            window_end=now,
            synced_at=now,
        )

    def self_report(self, user: User, tags: list[StrengthTag]) -> UserCard:
        stable = self._session.get(Portrait, (user.id, PortraitHorizon.STABLE.value))
        if (
            stable is not None
            and stable.strengths
            and stable.source in _OBSERVED_SOURCES
        ):
            raise BizException("已有知乎画像，不能自报覆盖", code=BizCode.CONFLICT)
        now = datetime.now(UTC)
        unique = list(dict.fromkeys(tags))
        self._upsert_portrait(
            user.id,
            PortraitHorizon.STABLE,
            unique,
            [],
            source=PortraitSource.SELF_REPORTED,
            window_start=None,
            window_end=None,
            synced_at=now,
        )
        if self._session.get(Portrait, (user.id, PortraitHorizon.RECENT_7D.value)) is None:
            self._upsert_portrait(
                user.id,
                PortraitHorizon.RECENT_7D,
                [],
                [],
                source=PortraitSource.CONTENTS,
                window_start=now - timedelta(days=PORTRAIT_RECENT_DAYS),
                window_end=now,
                synced_at=now,
            )
        self._session.flush()
        return self.get_card(user)

    def _upsert_user(self, profile: ZhihuProfile) -> User:
        user = self._session.scalar(
            select(User).where(User.zhihu_url_token == profile.url_token)
        )
        now = datetime.now(UTC)
        if user is None:
            user = User(
                zhihu_url_token=profile.url_token,
                zhihu_open_id=profile.open_id,
                display_name=profile.name,
                avatar_url=profile.avatar_url,
                headline=profile.headline,
                status=UserStatus.ACTIVE,
                last_login_at=now,
            )
            self._session.add(user)
            self._session.flush()
            return user
        user.display_name = profile.name
        user.avatar_url = profile.avatar_url
        user.headline = profile.headline
        if profile.open_id:
            user.zhihu_open_id = profile.open_id
        user.last_login_at = now
        self._session.flush()
        return user

    def _upsert_portrait(
        self,
        user_id: uuid.UUID,
        kind: PortraitHorizon,
        tags: list[StrengthTag],
        evidence: list[dict],
        *,
        source: PortraitSource,
        window_start: datetime | None,
        window_end: datetime | None,
        synced_at: datetime,
    ) -> None:
        row = self._session.get(Portrait, (user_id, kind.value))
        payload = [tag.value for tag in tags]
        if row is None:
            self._session.add(
                Portrait(
                    user_id=user_id,
                    kind=kind.value,
                    strengths=payload,
                    source=source.value,
                    evidence=evidence,
                    window_start=window_start,
                    window_end=window_end,
                    synced_at=synced_at,
                )
            )
            return
        row.strengths = payload
        row.source = source.value
        row.evidence = evidence
        row.window_start = window_start
        row.window_end = window_end
        row.synced_at = synced_at


def _to_view(row: Portrait) -> PortraitView:
    strengths: list[Strength] = []
    source = PortraitSource(row.source)
    for raw in row.strengths or []:
        try:
            tag = StrengthTag(raw)
        except ValueError:
            continue
        strengths.append(Strength(tag=tag, source=source))
    return PortraitView(horizon=PortraitHorizon(row.kind), strengths=strengths)


_OBSERVED_SOURCES = frozenset(
    {PortraitSource.CONTENTS.value, PortraitSource.FAVORITES.value}
)


def _safe_list(label: str, fn) -> list:
    try:
        return fn()
    except Exception:
        logger.exception("知乎%s拉取失败，跳过这一路", label)
        return []


def _portrait_source(*, from_contents: bool, from_favorites: bool) -> PortraitSource:
    if from_contents:
        return PortraitSource.CONTENTS
    if from_favorites:
        return PortraitSource.FAVORITES
    return PortraitSource.CONTENTS


def _from_all(
    contents: list[ZhihuContent],
    followees: list[ZhihuFollowee],
    favorites: list[ZhihuCollection],
) -> tuple[list[StrengthTag], list[dict], PortraitSource]:
    tags: list[StrengthTag] = []
    evidence: list[dict] = []
    from_contents = False
    from_favorites = False
    for item in contents:
        hit = tags_from_text(item.title, item.summary)
        if hit:
            from_contents = True
            _extend_unique(tags, hit)
            _push_evidence(evidence, item.title, item.url, item.content_type)
    for item in favorites:
        hit = tags_from_text(item.title, item.summary, item.extra_text)
        if hit:
            from_favorites = True
            _extend_unique(tags, hit)
            _push_evidence(evidence, item.title, item.url, "collection")
    for item in followees:
        hit = tags_from_text(item.fullname, item.headline)
        if hit:
            from_contents = True
            _extend_unique(tags, hit)
    return tags, evidence[:5], _portrait_source(
        from_contents=from_contents, from_favorites=from_favorites
    )


def _from_recent(
    contents: list[ZhihuContent],
    favorites: list[ZhihuCollection],
    recent_start: datetime,
) -> tuple[list[StrengthTag], list[dict], PortraitSource]:
    start_ts = int(recent_start.timestamp())
    tags: list[StrengthTag] = []
    evidence: list[dict] = []
    from_contents = False
    from_favorites = False
    for item in contents:
        if item.created_at < start_ts:
            continue
        hit = tags_from_text(item.title, item.summary)
        if hit:
            from_contents = True
            _extend_unique(tags, hit)
            _push_evidence(evidence, item.title, item.url, item.content_type)
    for item in favorites:
        if item.fav_time < start_ts:
            continue
        hit = tags_from_text(item.title, item.summary, item.extra_text)
        if hit:
            from_favorites = True
            _extend_unique(tags, hit)
            _push_evidence(evidence, item.title, item.url, "collection")
    return tags, evidence[:5], _portrait_source(
        from_contents=from_contents, from_favorites=from_favorites
    )


def _extend_unique(bucket: list[StrengthTag], found: list[StrengthTag]) -> None:
    for tag in found:
        if tag not in bucket:
            bucket.append(tag)


def _push_evidence(bucket: list[dict], title: str, url: str, content_type: str) -> None:
    if len(bucket) >= 5:
        return
    bucket.append({"title": title, "url": url, "content_type": content_type})
