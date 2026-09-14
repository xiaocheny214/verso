"""从授权数据源抽取擅长画像。不负责登录。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.portrait.models import Portrait
from verso_app.server.portrait.ports import GrantReader
from verso_app.server.portrait.tagger import tags_from_text
from verso_common.constants import PORTRAIT_RECENT_DAYS
from verso_common.enums import BizCode, PortraitHorizon, PortraitSource, StrengthTag
from verso_common.exceptions import BizException
from verso_common.models import PortraitView, Strength, UserCard
from verso_framework.providers.zhihu import (
    UserDataClient,
    ZhihuCollection,
    ZhihuContent,
    ZhihuFollowee,
)

logger = logging.getLogger("verso.portrait")


class PortraitService:
    def __init__(
        self,
        session: Session,
        grants: GrantReader,
        zhihu: UserDataClient,
    ) -> None:
        self._session = session
        self._grants = grants
        self._zhihu = zhihu

    def card_for(self, user: User) -> UserCard:
        portraits = self._session.scalars(select(Portrait).where(Portrait.user_id == user.id)).all()
        views = [_to_view(row) for row in portraits]
        views.sort(key=lambda item: item.horizon.value)
        return UserCard(
            id=str(user.id),
            name=user.display_name,
            avatar_url=user.avatar_url,
            portraits=views,
        )

    def sync(self, user_id: uuid.UUID) -> None:
        grant = self._grants.load_grant(str(user_id))
        if not grant:
            raise BizException("授权已过期，请重新登录", code=BizCode.UNAUTHORIZED)
        contents = _try_list("创作", lambda: self._zhihu.list_contents(grant))
        followees = _try_list("关注", lambda: self._zhihu.list_followees(grant))
        favorites = _try_list("收藏", lambda: self._zhihu.list_favorites(grant))
        any_ok = contents.ok or followees.ok or favorites.ok
        all_ok = contents.ok and followees.ok and favorites.ok
        if not any_ok:
            logger.warning("知乎画像三路都失败，保留已有画像 user_id=%s", user_id)
            raise BizException("画像同步失败，请稍后重试", code=BizCode.INTERNAL_ERROR)
        now = datetime.now(UTC)
        recent_start = now - timedelta(days=PORTRAIT_RECENT_DAYS)
        stable_tags, stable_evidence, stable_source = _from_all(
            contents.items, followees.items, favorites.items
        )
        recent_tags, recent_evidence, recent_source = _from_recent(
            contents.items, favorites.items, recent_start
        )
        if not all_ok and not stable_tags and not recent_tags:
            logger.warning("知乎部分接口失败且抽不出擅长，保留已有画像 user_id=%s", user_id)
            return
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
        if stable is not None and stable.strengths and stable.source in _OBSERVED_SOURCES:
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
        return self.card_for(user)

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


_OBSERVED_SOURCES = frozenset({PortraitSource.CONTENTS.value, PortraitSource.FAVORITES.value})


@dataclass(frozen=True, slots=True)
class _Fetch:
    items: list
    ok: bool


def _try_list(label: str, fn) -> _Fetch:
    try:
        return _Fetch(items=fn(), ok=True)
    except Exception:
        logger.exception("知乎%s拉取失败，跳过这一路", label)
        return _Fetch(items=[], ok=False)


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
    return (
        tags,
        evidence[:5],
        _portrait_source(from_contents=from_contents, from_favorites=from_favorites),
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
    return (
        tags,
        evidence[:5],
        _portrait_source(from_contents=from_contents, from_favorites=from_favorites),
    )


def _extend_unique(bucket: list[StrengthTag], found: list[StrengthTag]) -> None:
    for tag in found:
        if tag not in bucket:
            bucket.append(tag)


def _push_evidence(bucket: list[dict], title: str, url: str, content_type: str) -> None:
    if len(bucket) >= 5:
        return
    bucket.append({"title": title, "url": url, "content_type": content_type})
