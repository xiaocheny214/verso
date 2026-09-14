"""成色开户与加减分。只有这里改分；quality 按裁决调用。"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session
from verso_common.constants import (
    REPUTATION_GOOD_DELTA,
    REPUTATION_INITIAL_SCORE,
    REPUTATION_MIN_ACTIVE_SCORE,
    REPUTATION_POOR_DELTA,
    REPUTATION_SCORE_MAX,
)
from verso_common.enums import Eligibility
from verso_common.models import ReputationView
from verso_framework.config.app import AppSettings

from verso_app.server.reputation.models import Reputation


class ReputationService:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self._score_max = (
            settings.reputation_score_max if settings is not None else REPUTATION_SCORE_MAX
        )
        self._initial_score = (
            settings.reputation_initial_score
            if settings is not None
            else REPUTATION_INITIAL_SCORE
        )
        self._poor_delta = (
            settings.reputation_poor_delta if settings is not None else REPUTATION_POOR_DELTA
        )
        self._good_delta = (
            settings.reputation_good_delta if settings is not None else REPUTATION_GOOD_DELTA
        )
        self._min_active_score = (
            settings.reputation_min_active_score
            if settings is not None
            else REPUTATION_MIN_ACTIVE_SCORE
        )

    def ensure_default(self, session: Session, user_id: uuid.UUID) -> None:
        row = session.get(Reputation, user_id)
        if row is not None:
            return
        session.add(
            Reputation(
                user_id=user_id,
                score=self._initial_score,
                eligibility=Eligibility.ACTIVE,
            )
        )

    def apply_poor(self, session: Session, user_id: uuid.UUID) -> None:
        self._add(session, user_id, -self._poor_delta)

    def apply_good(self, session: Session, user_id: uuid.UUID) -> None:
        self._add(session, user_id, self._good_delta)

    def get_view(self, session: Session, user_id: uuid.UUID) -> ReputationView:
        self.ensure_default(session, user_id)
        session.flush()
        row = session.get(Reputation, user_id)
        if row is None:
            return ReputationView(
                score=self._initial_score,
                score_max=self._score_max,
                min_active_score=self._min_active_score,
            )
        return ReputationView(
            score=row.score,
            score_max=self._score_max,
            min_active_score=self._min_active_score,
            eligibility=Eligibility(row.eligibility),
            suspended_until=row.suspended_until,
        )

    def score_of(self, session: Session, user_id: uuid.UUID) -> int:
        row = session.get(Reputation, user_id)
        return row.score if row is not None else self._initial_score

    def allows_match(
        self, session: Session, user_id: uuid.UUID, now: datetime
    ) -> bool:
        row = session.get(Reputation, user_id)
        if row is None:
            return False
        if row.eligibility != Eligibility.ACTIVE:
            return False
        if row.score < self._min_active_score:
            return False
        return row.suspended_until is None or row.suspended_until <= now

    def _add(self, session: Session, user_id: uuid.UUID, delta: int) -> None:
        self.ensure_default(session, user_id)
        row = session.get(Reputation, user_id)
        if row is None:
            return
        row.score = min(self._score_max, max(0, row.score + delta))
        session.flush()
