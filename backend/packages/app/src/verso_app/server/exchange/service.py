"""一对关系及其下的多轮留言。关系来自 match，消息只属于这一对。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from verso_common.enums import BizCode, ExchangeStatus, StrengthTag
from verso_common.exceptions import BizException
from verso_common.models import ExchangeView, MessageView, PairView

from verso_app.server.auth.models import User
from verso_app.server.exchange.models import Exchange, Message
from verso_app.server.match.models import MatchCondition
from verso_app.server.portrait.models import Portrait


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class ExchangeService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def open(
        self,
        *,
        pair_id: uuid.UUID,
        user_a_id: uuid.UUID,
        user_b_id: uuid.UUID,
        closes_at: datetime,
    ) -> None:
        existing = self._session.get(Exchange, pair_id)
        if existing is not None:
            return
        now = datetime.now(UTC)
        self._session.add(
            Exchange(
                id=pair_id,
                user_a_id=user_a_id,
                user_b_id=user_b_id,
                status=ExchangeStatus.OPEN.value,
                opened_at=now,
                closes_at=closes_at,
            )
        )
        self._session.flush()

    def list_mine(self, user: User) -> list[PairView]:
        now = datetime.now(UTC)
        self.expire_open(now)
        rows = self._session.scalars(
            select(Exchange)
            .where(or_(Exchange.user_a_id == user.id, Exchange.user_b_id == user.id))
            .order_by(Exchange.opened_at.desc())
        ).all()
        return [self._to_pair(row, user.id) for row in rows]

    def get(self, user: User, exchange_id: uuid.UUID) -> ExchangeView:
        now = datetime.now(UTC)
        self.expire_open(now)
        row = self._require_member(user, exchange_id)
        return self._to_view(row)

    def list_messages(self, user: User, exchange_id: uuid.UUID) -> list[MessageView]:
        now = datetime.now(UTC)
        self.expire_open(now)
        self._require_member(user, exchange_id)
        rows = self._session.scalars(
            select(Message)
            .where(Message.exchange_id == exchange_id)
            .order_by(Message.created_at.asc())
        ).all()
        return [self._to_message(row) for row in rows]

    def send(self, user: User, exchange_id: uuid.UUID, *, text: str) -> MessageView:
        body = text.strip()
        if not body:
            raise BizException("请填写留言", code=BizCode.BAD_REQUEST)
        now = datetime.now(UTC)
        self.expire_open(now)
        row = self._require_open(user, exchange_id, now)
        message = Message(
            exchange_id=row.id,
            sender_id=user.id,
            text=body,
            created_at=now,
        )
        self._session.add(message)
        self._session.flush()
        return self._to_message(message)

    def close(self, user: User, exchange_id: uuid.UUID) -> ExchangeView:
        now = datetime.now(UTC)
        self.expire_open(now)
        row = self._require_member(user, exchange_id)
        if row.status != ExchangeStatus.OPEN.value:
            raise BizException("这对已经结束", code=BizCode.CONFLICT)
        row.status = ExchangeStatus.CLOSED.value
        row.closed_at = now
        self._session.flush()
        return self._to_view(row)

    def expire_open(self, now: datetime | None = None) -> int:
        moment = now or datetime.now(UTC)
        rows = self._session.scalars(
            select(Exchange).where(Exchange.status == ExchangeStatus.OPEN.value)
        ).all()
        closed = 0
        for row in rows:
            if _aware(row.closes_at) > moment:
                continue
            row.status = ExchangeStatus.CLOSED.value
            row.closed_at = moment
            closed += 1
        if closed:
            self._session.flush()
        return closed

    def _require_member(self, user: User, exchange_id: uuid.UUID) -> Exchange:
        row = self._session.get(Exchange, exchange_id)
        if row is None:
            raise BizException("没有这对关系", code=BizCode.NOT_FOUND)
        if user.id not in (row.user_a_id, row.user_b_id):
            raise BizException("没有这对关系", code=BizCode.NOT_FOUND)
        return row

    def _require_open(self, user: User, exchange_id: uuid.UUID, now: datetime) -> Exchange:
        row = self._require_member(user, exchange_id)
        if row.status != ExchangeStatus.OPEN.value or _aware(row.closes_at) <= now:
            raise BizException("这对已经结束，不能再留言", code=BizCode.CONFLICT)
        return row

    def _to_view(self, row: Exchange) -> ExchangeView:
        return ExchangeView(
            id=str(row.id),
            user_a_id=str(row.user_a_id),
            user_b_id=str(row.user_b_id),
            status=ExchangeStatus(row.status),
            opened_at=row.opened_at,
            closes_at=row.closes_at,
            closed_at=row.closed_at,
        )

    def _to_message(self, row: Message) -> MessageView:
        return MessageView(
            id=str(row.id),
            exchange_id=str(row.exchange_id),
            sender_id=str(row.sender_id),
            text=row.text,
            created_at=row.created_at,
        )

    def _to_pair(self, row: Exchange, viewer_id: uuid.UUID) -> PairView:
        peer_id = row.user_b_id if row.user_a_id == viewer_id else row.user_a_id
        peer = self._session.get(User, peer_id)
        want = self._session.scalar(
            select(MatchCondition).where(
                MatchCondition.pair_id == row.id,
                MatchCondition.user_id == peer_id,
            )
        )
        return PairView(
            exchange_id=str(row.id),
            peer_id=str(peer_id),
            peer_name=peer.display_name if peer else "",
            peer_avatar_url=peer.avatar_url if peer else None,
            peer_strengths=self._strengths(peer_id),
            peer_want_text=want.want_text if want else "",
        )

    def _strengths(self, user_id: uuid.UUID) -> list[StrengthTag]:
        rows = self._session.scalars(
            select(Portrait).where(Portrait.user_id == user_id)
        ).all()
        tags: list[StrengthTag] = []
        seen: set[str] = set()
        for row in rows:
            for raw in row.strengths or []:
                key = str(raw)
                if key in seen:
                    continue
                try:
                    tags.append(StrengthTag(raw))
                except ValueError:
                    continue
                seen.add(key)
        return tags
