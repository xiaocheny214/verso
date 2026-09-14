"""这次想学什么 + 双向互补配对。擅长只读 portrait。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.exchange.ports import ExchangeOpener, NoopExchangeOpener
from verso_app.server.match.compatibility import (
    MAX_COMPATIBILITY_CANDIDATES,
    CapabilityEvidence,
    DirectionInput,
    PairCompatibilityEvaluator,
    TagOnlyCompatibilityEvaluator,
)
from verso_app.server.match.models import MatchCondition
from verso_app.server.portrait.models import Portrait
from verso_app.server.reputation.service import ReputationService
from verso_common.constants import MATCH_WAIT_HOURS, PAIR_WINDOW_HOURS
from verso_common.enums import BizCode, MatchConditionStatus, StrengthTag
from verso_common.exceptions import BizException
from verso_common.models import MatchConditionView, MatchPeerView


class MatchService:
    def __init__(
        self,
        session: Session,
        *,
        exchange: ExchangeOpener | None = None,
        reputation: ReputationService | None = None,
        compatibility: PairCompatibilityEvaluator | None = None,
    ) -> None:
        self._session = session
        self._exchange = exchange or NoopExchangeOpener()
        self._reputation = reputation or ReputationService()
        self._compatibility = compatibility or TagOnlyCompatibilityEvaluator()

    def submit(self, user: User, *, want_text: str, want_tag: StrengthTag) -> MatchConditionView:
        text = want_text.strip()
        if not text:
            raise BizException("请填写这次想学什么", code=BizCode.BAD_REQUEST)
        now = datetime.now(UTC)
        self.expire_waiting(now)
        self._assert_eligible(user.id, now)
        self._assert_can_enter(user.id, now)
        row = MatchCondition(
            user_id=user.id,
            want_text=text,
            want_tag=want_tag.value,
            status=MatchConditionStatus.WAITING.value,
            waiting_until=now + timedelta(hours=MATCH_WAIT_HOURS),
        )
        self._session.add(row)
        self._session.flush()
        self._try_pair(row, now)
        self._session.flush()
        return self._to_view(row)

    def current(self, user: User) -> MatchConditionView:
        now = datetime.now(UTC)
        self.expire_waiting(now)
        row = self._open_condition(user.id, now)
        if row is None:
            raise BizException("没有正在进行的匹配", code=BizCode.NOT_FOUND)
        return self._to_view(row)

    def cancel(self, user: User) -> MatchConditionView:
        now = datetime.now(UTC)
        self.expire_waiting(now)
        row = self._session.scalar(
            select(MatchCondition).where(
                MatchCondition.user_id == user.id,
                MatchCondition.status == MatchConditionStatus.WAITING.value,
            )
        )
        if row is None:
            raise BizException("没有等待中的匹配", code=BizCode.CONFLICT)
        row.status = MatchConditionStatus.CANCELLED.value
        self._session.flush()
        return self._to_view(row)

    def expire_waiting(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        rows = self._session.scalars(
            select(MatchCondition).where(
                MatchCondition.status == MatchConditionStatus.WAITING.value,
                MatchCondition.waiting_until.is_not(None),
                MatchCondition.waiting_until <= moment,
            )
        ).all()
        for row in rows:
            row.status = MatchConditionStatus.CANCELLED.value
        if rows:
            self._session.flush()
        return len(rows)

    def _try_pair(self, mine: MatchCondition, now: datetime) -> None:
        my_strengths = self._strengths(mine.user_id)
        my_score = self._reputation.score_of(self._session, mine.user_id)
        candidates = self._session.scalars(
            select(MatchCondition)
            .where(
                MatchCondition.status == MatchConditionStatus.WAITING.value,
                MatchCondition.user_id != mine.user_id,
                MatchCondition.pair_id.is_(None),
                MatchCondition.waiting_until.is_not(None),
                MatchCondition.waiting_until > now,
            )
            .order_by(MatchCondition.created_at.asc())
        ).all()
        compatible: list[MatchCondition] = []
        for other in candidates:
            if other.want_tag == mine.want_tag:
                continue
            if not self._is_eligible(other.user_id, now):
                continue
            other_strengths = self._strengths(other.user_id)
            if mine.want_tag not in other_strengths or other.want_tag not in my_strengths:
                continue
            compatible.append(other)
        compatible.sort(
            key=lambda other: (
                abs(my_score - self._reputation.score_of(self._session, other.user_id)),
                other.created_at,
            )
        )
        for other in compatible[:MAX_COMPATIBILITY_CANDIDATES]:
            if not self._supports_specific_pair(mine, other):
                continue
            locked = self._lock_waiting(other.id, now)
            if locked is None:
                continue
            if self._claim_pair(mine, locked, now):
                return

    def _supports_specific_pair(
        self,
        mine: MatchCondition,
        other: MatchCondition,
    ) -> bool:
        mine_wants = StrengthTag(mine.want_tag)
        other_wants = StrengthTag(other.want_tag)
        directions = (
            DirectionInput(
                id=f"{other.user_id}:{mine.id}",
                question=mine.want_text,
                requested_tag=mine_wants,
                candidate_evidence=self._capability_evidence(other.user_id, mine_wants),
            ),
            DirectionInput(
                id=f"{mine.user_id}:{other.id}",
                question=other.want_text,
                requested_tag=other_wants,
                candidate_evidence=self._capability_evidence(mine.user_id, other_wants),
            ),
        )
        return self._compatibility.allows(directions)

    def _lock_waiting(self, condition_id: uuid.UUID, now: datetime) -> MatchCondition | None:
        stmt = select(MatchCondition).where(
            MatchCondition.id == condition_id,
            MatchCondition.status == MatchConditionStatus.WAITING.value,
            MatchCondition.pair_id.is_(None),
            MatchCondition.waiting_until.is_not(None),
            MatchCondition.waiting_until > now,
        )
        if self._session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        return self._session.scalar(stmt)

    def _claim_pair(self, left: MatchCondition, right: MatchCondition, now: datetime) -> bool:
        pair_id = uuid.uuid4()
        closes_at = now + timedelta(hours=PAIR_WINDOW_HOURS)
        nested = self._session.begin_nested()
        result = self._session.execute(
            update(MatchCondition)
            .where(
                MatchCondition.id.in_((left.id, right.id)),
                MatchCondition.status == MatchConditionStatus.WAITING.value,
                MatchCondition.pair_id.is_(None),
            )
            .values(
                status=MatchConditionStatus.MATCHED.value,
                pair_id=pair_id,
                pair_closes_at=closes_at,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 2:
            nested.rollback()
            self._session.expire(left)
            self._session.expire(right)
            return False
        nested.commit()
        for row in (left, right):
            row.status = MatchConditionStatus.MATCHED.value
            row.pair_id = pair_id
            row.pair_closes_at = closes_at
        self._exchange.open(
            pair_id=pair_id,
            user_a_id=left.user_id,
            user_b_id=right.user_id,
            closes_at=closes_at,
        )
        return True

    def _assert_eligible(self, user_id: uuid.UUID, now: datetime) -> None:
        if not self._is_eligible(user_id, now):
            raise BizException("当前不能配对", code=BizCode.CONFLICT)

    def _is_eligible(self, user_id: uuid.UUID, now: datetime) -> bool:
        return self._reputation.allows_match(self._session, user_id, now)

    def _assert_can_enter(self, user_id: uuid.UUID, now: datetime) -> None:
        if self._open_condition(user_id, now) is not None:
            raise BizException("已有未关闭的匹配条件", code=BizCode.CONFLICT)

    def _open_condition(self, user_id: uuid.UUID, now: datetime) -> MatchCondition | None:
        waiting = self._session.scalar(
            select(MatchCondition).where(
                MatchCondition.user_id == user_id,
                MatchCondition.status == MatchConditionStatus.WAITING.value,
                MatchCondition.waiting_until.is_not(None),
                MatchCondition.waiting_until > now,
            )
        )
        if waiting is not None:
            return waiting
        return self._session.scalar(
            select(MatchCondition).where(
                MatchCondition.user_id == user_id,
                MatchCondition.status == MatchConditionStatus.MATCHED.value,
                MatchCondition.pair_closes_at.is_not(None),
                MatchCondition.pair_closes_at > now,
            )
        )

    def _strengths(self, user_id: uuid.UUID) -> set[str]:
        rows = self._session.scalars(select(Portrait).where(Portrait.user_id == user_id)).all()
        tags: set[str] = set()
        for row in rows:
            for raw in row.strengths or []:
                tags.add(str(raw))
        return tags

    def _capability_evidence(
        self,
        user_id: uuid.UUID,
        tag: StrengthTag,
    ) -> tuple[CapabilityEvidence, ...]:
        rows = self._session.scalars(select(Portrait).where(Portrait.user_id == user_id)).all()
        evidence_by_id: dict[str, CapabilityEvidence] = {}
        for row in rows:
            for raw in row.evidence or []:
                if not isinstance(raw, dict) or raw.get("tag") != tag.value:
                    continue
                title = str(raw.get("title") or "").strip()
                url = str(raw.get("url") or "").strip()
                if not title:
                    continue
                evidence_id = _capability_evidence_id(tag, title, url)
                try:
                    confidence = int(raw.get("confidence") or 0)
                except (TypeError, ValueError):
                    confidence = 0
                evidence_by_id[evidence_id] = CapabilityEvidence(
                    id=evidence_id,
                    title=title,
                    url=url,
                    reason=str(raw.get("reason") or ""),
                    confidence=max(0, min(confidence, 100)),
                )
        return tuple(
            sorted(
                evidence_by_id.values(),
                key=lambda item: (-item.confidence, item.id),
            )
        )

    def _to_view(self, row: MatchCondition) -> MatchConditionView:
        return MatchConditionView(
            id=str(row.id),
            want_text=row.want_text,
            want_tag=StrengthTag(row.want_tag),
            status=MatchConditionStatus(row.status),
            pair_id=str(row.pair_id) if row.pair_id else None,
            waiting_until=row.waiting_until,
            pair_closes_at=row.pair_closes_at,
            peer=self._peer_view(row),
        )

    def _peer_view(self, row: MatchCondition) -> MatchPeerView | None:
        if row.pair_id is None:
            return None
        peer_row = self._session.scalar(
            select(MatchCondition).where(
                MatchCondition.pair_id == row.pair_id,
                MatchCondition.user_id != row.user_id,
            )
        )
        if peer_row is None:
            return None
        peer = self._session.get(User, peer_row.user_id)
        if peer is None:
            return None
        strengths: list[StrengthTag] = []
        for raw in sorted(self._strengths(peer.id)):
            try:
                strengths.append(StrengthTag(raw))
            except ValueError:
                continue
        return MatchPeerView(
            id=str(peer.id),
            name=peer.display_name,
            avatar_url=peer.avatar_url,
            want_text=peer_row.want_text,
            want_tag=StrengthTag(peer_row.want_tag),
            strengths=strengths,
            score=self._reputation.score_of(self._session, peer.id),
        )


def _capability_evidence_id(tag: StrengthTag, title: str, url: str) -> str:
    digest = sha256(f"{tag.value}\0{url}\0{title}".encode()).hexdigest()[:16]
    return f"portrait:{digest}"
