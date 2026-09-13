"""声望开户与扣分。只有这里改分；quality 只在 poor 时调用。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session
from verso_common.constants import REPUTATION_INITIAL_SCORE, REPUTATION_POOR_DELTA
from verso_common.enums import Eligibility

from verso_app.server.reputation.models import Reputation


class ReputationService:
    def ensure_default(self, session: Session, user_id: uuid.UUID) -> None:
        row = session.get(Reputation, user_id)
        if row is not None:
            return
        session.add(
            Reputation(
                user_id=user_id,
                score=REPUTATION_INITIAL_SCORE,
                eligibility=Eligibility.ACTIVE,
            )
        )

    def apply_poor(self, session: Session, user_id: uuid.UUID) -> None:
        self.ensure_default(session, user_id)
        row = session.get(Reputation, user_id)
        if row is None:
            return
        row.score = max(0, row.score - REPUTATION_POOR_DELTA)
        session.flush()
