"""声望开户。扣分接口留给 quality 的 feat。"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from verso_app.server.reputation.models import Reputation
from verso_common.constants import REPUTATION_INITIAL_SCORE
from verso_common.enums import Eligibility


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
