"""人先点不满意，再判定留言。只写 review；poor 扣成色、good 加成色。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from verso_common.enums import BizCode, ReviewVerdict
from verso_common.exceptions import BizException
from verso_common.models import ExchangeView, ReviewView

from verso_app.server.auth.models import User
from verso_app.server.exchange.service import ExchangeService
from verso_app.server.match.models import MatchCondition
from verso_app.server.quality.judge import UnclearJudge
from verso_app.server.quality.models import Review
from verso_app.server.quality.ports import AnswerJudge
from verso_app.server.reputation.service import ReputationService


class QualityService:
    def __init__(
        self,
        session: Session,
        *,
        exchange: ExchangeService,
        reputation: ReputationService | None = None,
        judge: AnswerJudge | None = None,
    ) -> None:
        self._session = session
        self._exchange = exchange
        self._reputation = reputation or ReputationService()
        self._judge = judge or UnclearJudge()

    def submit(self, user: User, exchange_id: uuid.UUID) -> ReviewView:
        pair = self._exchange.get(user, exchange_id)
        reviewee_id = self._peer_id(user, pair)
        existing = self._session.scalar(
            select(Review).where(
                Review.exchange_id == exchange_id,
                Review.reviewee_id == reviewee_id,
            )
        )
        if existing is not None:
            raise BizException("已经评估过对方", code=BizCode.CONFLICT)
        want_text = self._want_text(user.id, exchange_id)
        answer = self._answer_text(user, exchange_id, reviewee_id)
        judgement = self._judge.judge(want_text=want_text, answer=answer)
        review = Review(
            exchange_id=exchange_id,
            reviewer_id=user.id,
            reviewee_id=reviewee_id,
            verdict=judgement.verdict.value,
            score=judgement.score,
            reason=judgement.reason,
            want_text=want_text,
            answer_text=answer,
        )
        self._session.add(review)
        if judgement.verdict == ReviewVerdict.POOR:
            self._reputation.apply_poor(self._session, reviewee_id)
        elif judgement.verdict == ReviewVerdict.GOOD:
            self._reputation.apply_good(self._session, reviewee_id)
        self._session.flush()
        return self._to_view(review)

    def _peer_id(self, user: User, pair: ExchangeView) -> uuid.UUID:
        left = uuid.UUID(pair.user_a_id)
        right = uuid.UUID(pair.user_b_id)
        if user.id == left:
            return right
        if user.id == right:
            return left
        raise BizException("没有这对关系", code=BizCode.NOT_FOUND)

    def _want_text(self, reviewer_id: uuid.UUID, exchange_id: uuid.UUID) -> str:
        row = self._session.scalar(
            select(MatchCondition).where(
                MatchCondition.pair_id == exchange_id,
                MatchCondition.user_id == reviewer_id,
            )
        )
        return row.want_text if row is not None else ""

    def _answer_text(
        self, user: User, exchange_id: uuid.UUID, reviewee_id: uuid.UUID
    ) -> str:
        peer = str(reviewee_id)
        parts = [
            item.text
            for item in self._exchange.list_messages(user, exchange_id)
            if item.sender_id == peer
        ]
        if not parts:
            raise BizException("对方还没有留言", code=BizCode.CONFLICT)
        return "\n".join(parts)

    def _to_view(self, row: Review) -> ReviewView:
        return ReviewView(
            id=str(row.id),
            exchange_id=str(row.exchange_id),
            reviewer_id=str(row.reviewer_id),
            reviewee_id=str(row.reviewee_id),
            verdict=ReviewVerdict(row.verdict),
            score=row.score,
            reason=row.reason,
        )
