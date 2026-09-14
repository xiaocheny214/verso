"""从授权数据源抽取擅长画像。不负责登录。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.portrait.extractor import (
    EvidenceClassifier,
    EvidenceInput,
    EvidenceKind,
    RuleEvidenceClassifier,
    aggregate_portrait,
)
from verso_app.server.portrait.models import Portrait
from verso_app.server.portrait.ports import GrantReader
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
        classifier: EvidenceClassifier | None = None,
    ) -> None:
        self._session = session
        self._grants = grants
        self._zhihu = zhihu
        self._classifier = classifier or RuleEvidenceClassifier()

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
        evidence = _build_evidence(contents.items, followees.items, favorites.items)
        assessments = self._classifier.classify(evidence)
        stable = aggregate_portrait(evidence, assessments)
        recent = aggregate_portrait(evidence, assessments, since=recent_start)
        if not all_ok and not stable.tags and not recent.tags:
            logger.warning("知乎部分接口失败且抽不出擅长，保留已有画像 user_id=%s", user_id)
            return
        self._upsert_portrait(
            user_id,
            PortraitHorizon.STABLE,
            stable.tags,
            stable.evidence,
            source=stable.source,
            window_start=None,
            window_end=None,
            synced_at=now,
        )
        self._upsert_portrait(
            user_id,
            PortraitHorizon.RECENT_7D,
            recent.tags,
            recent.evidence,
            source=recent.source,
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
        evidence = next(
            (
                item
                for item in row.evidence or []
                if isinstance(item, dict) and item.get("tag") == tag.value
            ),
            None,
        )
        evidence_source = source
        if evidence and evidence.get("source"):
            try:
                evidence_source = PortraitSource(str(evidence["source"]))
            except ValueError:
                evidence_source = source
        strengths.append(
            Strength(
                tag=tag,
                source=evidence_source,
                evidence_title=str(evidence.get("title") or "") or None if evidence else None,
                evidence_url=str(evidence.get("url") or "") or None if evidence else None,
            )
        )
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


def _build_evidence(
    contents: list[ZhihuContent],
    followees: list[ZhihuFollowee],
    favorites: list[ZhihuCollection],
) -> list[EvidenceInput]:
    evidence: list[EvidenceInput] = []
    for item in contents:
        evidence.append(
            EvidenceInput(
                id=_evidence_id(EvidenceKind.CONTENT, item.url, item.title),
                kind=EvidenceKind.CONTENT,
                content_type=item.content_type,
                title=item.title,
                text=item.summary,
                url=item.url,
                observed_at=datetime.fromtimestamp(item.created_at, tz=UTC),
            )
        )
    for item in favorites:
        evidence.append(
            EvidenceInput(
                id=_evidence_id(EvidenceKind.FAVORITE, item.url, item.title),
                kind=EvidenceKind.FAVORITE,
                content_type="collection",
                title=item.title,
                text=" ".join(part for part in (item.summary, item.extra_text) if part),
                url=item.url,
                observed_at=datetime.fromtimestamp(item.fav_time, tz=UTC),
            )
        )
    for item in followees:
        evidence.append(
            EvidenceInput(
                id=_evidence_id(EvidenceKind.FOLLOWEE, item.url, item.fullname),
                kind=EvidenceKind.FOLLOWEE,
                content_type="followee",
                title=item.headline,
                text="",
                url=item.url,
                observed_at=None,
            )
        )
    return evidence


def _evidence_id(kind: EvidenceKind, url: str, title: str) -> str:
    digest = sha256(f"{kind.value}\0{url}\0{title}".encode()).hexdigest()[:16]
    return f"{kind.value}:{digest}"
