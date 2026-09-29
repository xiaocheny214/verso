"""这次想学什么 + 双向互补配对。擅长只读 portrait。"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.exchange.ports import ExchangeOpener, NoopExchangeOpener
from verso_app.server.knowledge.models import KnowledgeBase, KnowledgeDocument
from verso_app.server.knowledge.vector_store import (
    ChunkSearchResult,
    ChunkVectorStore,
)
from verso_app.server.match.compatibility import (
    MAX_COMPATIBILITY_CANDIDATES,
    CapabilityEvidence,
    CompatibilityVerdict,
    DirectionInput,
    PairCompatibilityEvaluator,
    TagOnlyCompatibilityEvaluator,
)
from verso_app.server.match.models import MatchCandidate, MatchCondition, MatchEvaluation
from verso_app.server.portrait.models import Portrait
from verso_app.server.reputation.service import ReputationService
from verso_common.constants import MATCH_WAIT_HOURS, PAIR_WINDOW_HOURS
from verso_common.enums import (
    BizCode,
    DocumentStatus,
    MatchConditionStatus,
    MatchEvaluationOutcome,
    StrengthTag,
)
from verso_common.exceptions import BizException
from verso_common.models import MatchConditionView, MatchPeerView
from verso_framework.config import AppSettings, get_app_settings
from verso_framework.embed import Embedder

logger = logging.getLogger("verso.match")


def _capability_band(score: int) -> int:
    """金字塔能力阶梯划分 (0-100)：
    Band 0: < 60
    Band 1: 60 - 69
    Band 2: 70 - 79
    Band 3: 80 - 89
    Band 4: >= 90
    """
    if score < 60:
        return 0
    if score < 70:
        return 1
    if score < 80:
        return 2
    if score < 90:
        return 3
    return 4


def _in_capability_band(score_a: int, score_b: int) -> bool:
    """双方必须处于相同或相邻能力阶梯。"""
    return abs(_capability_band(score_a) - _capability_band(score_b)) <= 1


class MatchService:
    def __init__(
        self,
        session: Session,
        *,
        exchange: ExchangeOpener | None = None,
        reputation: ReputationService | None = None,
        compatibility: PairCompatibilityEvaluator | None = None,
        embedder: Embedder | None = None,
        vector_store: ChunkVectorStore | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        self._session = session
        self._exchange = exchange or NoopExchangeOpener()
        self._reputation = reputation or ReputationService()
        self._compatibility = compatibility or TagOnlyCompatibilityEvaluator()
        self._embedder = embedder
        self._vector_store = vector_store
        self._settings = settings or get_app_settings()

    def submit(self, user: User, *, want_text: str, want_tag: StrengthTag) -> MatchConditionView:
        text = want_text.strip()
        if not text:
            raise BizException("请填写这次想学什么", code=BizCode.BAD_REQUEST)
        now = datetime.now(UTC)
        self.expire_waiting(now)
        self._assert_eligible(user.id, now)
        self._assert_can_enter(user.id, now)

        question_embedding: list[float] | None = None
        if self._embedder is not None:
            try:
                question_embedding = self._embedder.embed_query(text)
            except Exception:
                logger.warning("生成提问向量失败，跳过嵌入", exc_info=True)

        row = MatchCondition(
            user_id=user.id,
            want_text=text,
            want_tag=want_tag.value,
            status=MatchConditionStatus.WAITING.value,
            waiting_until=now + timedelta(hours=MATCH_WAIT_HOURS),
            question_embedding=question_embedding,
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
        self._clean_candidates(condition_ids=[row.id], user_ids=[row.user_id])
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
        expired_ids = [row.id for row in rows]
        expired_user_ids = [row.user_id for row in rows]
        for row in rows:
            row.status = MatchConditionStatus.CANCELLED.value
        if expired_ids:
            self._clean_candidates(condition_ids=expired_ids, user_ids=expired_user_ids)
            self._session.flush()
        return len(rows)

    def _clean_candidates(
        self,
        condition_ids: list[uuid.UUID] | None = None,
        user_ids: list[uuid.UUID] | None = None,
    ) -> None:
        """清理已离开 waiting 状态相关的候选记录。

        不仅清理作为提问者 (question_id) 的候选，也要清理作为 helper (helper_id) 的候选，
        避免已配对或已退出的用户切片被其他等待中提问者自连接召回。
        """
        clauses = []
        if condition_ids:
            clauses.append(MatchCandidate.question_id.in_(condition_ids))
        if user_ids:
            clauses.append(MatchCandidate.helper_id.in_(user_ids))
        if not clauses:
            return
        self._session.execute(delete(MatchCandidate).where(or_(*clauses)))

    def _try_pair(self, mine: MatchCondition, now: datetime) -> None:
        my_strengths = self._strengths(mine.user_id)
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

        # 硬性互补与资格过滤
        s_candidates: list[MatchCondition] = []
        for other in candidates:
            if other.want_tag == mine.want_tag:
                continue
            if not self._is_eligible(other.user_id, now):
                continue
            other_strengths = self._strengths(other.user_id)
            if mine.want_tag not in other_strengths or other.want_tag not in my_strengths:
                continue
            s_candidates.append(other)

        if not s_candidates:
            return

        if self._vector_store is None:
            self._fallback_try_pair(mine, s_candidates, now)
            return

        # 执行单向 RAG 写入 (Forward Search & Reverse Scoring)
        self._populate_candidates(mine, s_candidates)

        # 自连接与能力阶梯金字塔配对
        paired = self._try_pair_from_candidates(mine, s_candidates, now)
        if paired:
            return

        # 若未配对成功，检查回退机制
        if self._settings.match_title_fallback_when_no_ready:
            # 只有当没人拥有已就绪切片时，才回退到基于画像标题的匹配
            all_user_ids = {mine.user_id} | {c.user_id for c in s_candidates}
            ready_doc_count = (
                self._session.scalar(
                    select(func.count(KnowledgeDocument.id))
                    .join(KnowledgeBase, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
                    .where(
                        KnowledgeBase.user_id.in_(all_user_ids),
                        KnowledgeDocument.status == DocumentStatus.SUCCESS,
                    )
                )
                or 0
            )
            if ready_doc_count == 0:
                self._fallback_try_pair(mine, s_candidates, now)

    def _populate_candidates(
        self, mine: MatchCondition, s_candidates: list[MatchCondition]
    ) -> None:
        if self._vector_store is None:
            return

        min_score = self._settings.match_retrieval_min_score
        top_k = self._settings.match_retrieval_top_k

        # 1. 正向检索：用 mine.question_embedding 检索 S 中各候选人的切片
        if mine.question_embedding:
            s_user_ids = {other.user_id for other in s_candidates}
            # 查询 S 中具有就绪文档切片的用户
            ready_s_users = set(
                self._session.scalars(
                    select(KnowledgeBase.user_id)
                    .join(
                        KnowledgeDocument, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id
                    )
                    .where(
                        KnowledgeBase.user_id.in_(s_user_ids),
                        KnowledgeDocument.status == DocumentStatus.SUCCESS,
                    )
                ).all()
            )
            if ready_s_users:
                hits = self._vector_store.search_chunks(
                    query_embedding=mine.question_embedding,
                    user_ids=ready_s_users,
                    top_k=top_k,
                    min_score=min_score,
                )
                # 每个 helper 保留最高分 hit
                best_hits_by_user: dict[uuid.UUID, ChunkSearchResult] = {}
                for hit in hits:
                    if (
                        hit.user_id not in best_hits_by_user
                        or hit.score > best_hits_by_user[hit.user_id].score
                    ):
                        best_hits_by_user[hit.user_id] = hit

                for helper_id, best_hit in best_hits_by_user.items():
                    evidence_payload = {
                        "article_id": str(best_hit.document_id),
                        "chunk_index": best_hit.chunk_index,
                        "title": best_hit.metadata.get("title", ""),
                        "url": best_hit.metadata.get("source_url", ""),
                        "score": best_hit.score,
                    }
                    self._upsert_candidate(
                        question_id=mine.id,
                        helper_id=helper_id,
                        score=best_hit.score,
                        evidence=evidence_payload,
                    )

        # 2. 反向局部打分：若当前用户有就绪文档切片，遍历 S 中的已有条件
        my_has_ready = bool(
            self._session.scalar(
                select(KnowledgeDocument.id)
                .join(KnowledgeBase, KnowledgeDocument.knowledge_base_id == KnowledgeBase.id)
                .where(
                    KnowledgeBase.user_id == mine.user_id,
                    KnowledgeDocument.status == DocumentStatus.SUCCESS,
                )
                .limit(1)
            )
        )
        if my_has_ready:
            for other in s_candidates:
                if not other.question_embedding:
                    continue
                hits = self._vector_store.search_chunks(
                    query_embedding=other.question_embedding,
                    user_ids={mine.user_id},
                    top_k=top_k,
                    min_score=min_score,
                )
                if hits:
                    best_hit = max(hits, key=lambda h: h.score)
                    if best_hit.score >= min_score:
                        evidence_payload = {
                            "article_id": str(best_hit.document_id),
                            "chunk_index": best_hit.chunk_index,
                            "title": best_hit.metadata.get("title", ""),
                            "url": best_hit.metadata.get("source_url", ""),
                            "score": best_hit.score,
                        }
                        self._upsert_candidate(
                            question_id=other.id,
                            helper_id=mine.user_id,
                            score=best_hit.score,
                            evidence=evidence_payload,
                        )

    def _upsert_candidate(
        self,
        *,
        question_id: uuid.UUID,
        helper_id: uuid.UUID,
        score: float,
        evidence: dict,
    ) -> None:
        existing = self._session.scalar(
            select(MatchCandidate).where(
                MatchCandidate.question_id == question_id,
                MatchCandidate.helper_id == helper_id,
            )
        )
        if existing is not None:
            existing.score = score
            existing.evidence = evidence
        else:
            cand = MatchCandidate(
                question_id=question_id,
                helper_id=helper_id,
                score=score,
                evidence=evidence,
            )
            self._session.add(cand)
        self._session.flush()

    def _try_pair_from_candidates(
        self, mine: MatchCondition, s_candidates: list[MatchCondition], now: datetime
    ) -> bool:
        """自连接查找互为帮手 (A helps B and B helps A)，并结合金字塔能力阶梯排序"""
        other_by_user_id = {c.user_id: c for c in s_candidates}
        other_by_cond_id = {c.id: c for c in s_candidates}

        # 查询 A 作为提问者、由其他人帮助的记录 (mine.id -> other.user_id)
        forward_cands = self._session.scalars(
            select(MatchCandidate).where(MatchCandidate.question_id == mine.id)
        ).all()
        forward_by_helper = {c.helper_id: c for c in forward_cands}

        # 查询其他人作为提问者、由 A 帮助的记录 (other.id -> mine.user_id)
        if other_by_cond_id:
            reverse_cands = self._session.scalars(
                select(MatchCandidate).where(
                    MatchCandidate.question_id.in_(list(other_by_cond_id.keys())),
                    MatchCandidate.helper_id == mine.user_id,
                )
            ).all()
        else:
            reverse_cands = []
        reverse_by_question = {c.question_id: c for c in reverse_cands}

        my_score = self._reputation.score_of(self._session, mine.user_id)

        # 自连接匹配对
        mutual_pairs: list[tuple[MatchCondition, float, int, datetime, dict, dict]] = []
        for helper_id, fwd in forward_by_helper.items():
            other = other_by_user_id.get(helper_id)
            if other is None:
                continue
            rev = reverse_by_question.get(other.id)
            if rev is None:
                continue

            other_score = self._reputation.score_of(self._session, other.user_id)
            # 金字塔能力阶梯过滤：双方必须在同层或相邻层
            if not _in_capability_band(my_score, other_score):
                continue

            pair_score = min(fwd.score, rev.score)
            rep_diff = abs(my_score - other_score)
            mutual_pairs.append(
                (other, pair_score, rep_diff, other.created_at, fwd.evidence, rev.evidence)
            )

        # 排序：pair_score 降序 > 声望差绝对值升序 > 等待时间较长（创建较早）
        mutual_pairs.sort(key=lambda item: (-item[1], item[2], item[3]))

        for other, _score, _diff, _time, fwd_evidence, rev_evidence in mutual_pairs[
            :MAX_COMPATIBILITY_CANDIDATES
        ]:
            if self._consider_rag_candidate(mine, other, fwd_evidence, rev_evidence, now):
                return True
        return False

    def _consider_rag_candidate(
        self,
        mine: MatchCondition,
        other: MatchCondition,
        mine_evidence_dict: dict,
        other_evidence_dict: dict,
        now: datetime,
    ) -> bool:
        """带 RAG 切片证据的双闸门评估"""
        directions = self._pair_rag_directions(mine, other, mine_evidence_dict, other_evidence_dict)
        verdict = self._model_verdict(directions)
        allowed = self._compatibility.allows(directions) if verdict is None else verdict.allowed
        if not allowed:
            if verdict is not None:
                self._record_evaluation(
                    mine,
                    other,
                    verdict,
                    verdict.outcome or MatchEvaluationOutcome.SKIPPED_ERROR,
                )
            return False
        locked = self._lock_waiting(other.id, now)
        if locked is None:
            if verdict is not None:
                self._record_evaluation(mine, other, verdict, MatchEvaluationOutcome.SKIPPED_LOCK)
            return False
        claimed = self._claim_pair(mine, locked, now)
        if verdict is not None:
            self._record_evaluation(
                mine,
                other,
                verdict,
                MatchEvaluationOutcome.PAIRED if claimed else MatchEvaluationOutcome.SKIPPED_LOCK,
            )
        if claimed:
            self._clean_candidates(
                condition_ids=[mine.id, other.id],
                user_ids=[mine.user_id, other.user_id],
            )
        return claimed

    def _pair_rag_directions(
        self,
        mine: MatchCondition,
        other: MatchCondition,
        mine_evidence_dict: dict,
        other_evidence_dict: dict,
    ) -> tuple[DirectionInput, DirectionInput]:
        """将切片证据排在最前面，并保留画像证据作为补充"""
        mine_wants = StrengthTag(mine.want_tag)
        other_wants = StrengthTag(other.want_tag)

        # other 帮助 mine 的切片证据
        other_chunk_evidence = self._to_chunk_evidence(mine_evidence_dict)
        other_portrait_evidence = self._capability_evidence(other.user_id, mine_wants)
        combined_other_evidence = (
            (other_chunk_evidence,) if other_chunk_evidence else ()
        ) + other_portrait_evidence

        # mine 帮助 other 的切片证据
        mine_chunk_evidence = self._to_chunk_evidence(other_evidence_dict)
        mine_portrait_evidence = self._capability_evidence(mine.user_id, other_wants)
        combined_mine_evidence = (
            (mine_chunk_evidence,) if mine_chunk_evidence else ()
        ) + mine_portrait_evidence

        return (
            DirectionInput(
                id=f"{other.user_id}:{mine.id}",
                question=mine.want_text,
                requested_tag=mine_wants,
                candidate_evidence=combined_other_evidence,
            ),
            DirectionInput(
                id=f"{mine.user_id}:{other.id}",
                question=other.want_text,
                requested_tag=other_wants,
                candidate_evidence=combined_mine_evidence,
            ),
        )

    def _to_chunk_evidence(self, evidence_dict: dict) -> CapabilityEvidence | None:
        if not evidence_dict or "article_id" not in evidence_dict:
            return None
        article_id = evidence_dict["article_id"]
        chunk_index = evidence_dict.get("chunk_index", 0)
        title = evidence_dict.get("title") or "文档切片"
        url = evidence_dict.get("url") or ""
        score = evidence_dict.get("score", 0.0)
        confidence = int(min(100, max(0, score * 100)))
        return CapabilityEvidence(
            id=f"article:{article_id}:c{chunk_index}",
            title=title,
            url=url,
            reason="文档切片语义匹配",
            confidence=confidence,
        )

    def _fallback_try_pair(
        self, mine: MatchCondition, compatible: list[MatchCondition], now: datetime
    ) -> None:
        my_score = self._reputation.score_of(self._session, mine.user_id)
        compatible_sorted = sorted(
            compatible,
            key=lambda other: (
                abs(my_score - self._reputation.score_of(self._session, other.user_id)),
                other.created_at,
            ),
        )
        for other in compatible_sorted[:MAX_COMPATIBILITY_CANDIDATES]:
            if self._consider_candidate(mine, other, now):
                return

    def _consider_candidate(
        self, mine: MatchCondition, other: MatchCondition, now: datetime
    ) -> bool:
        directions = self._pair_directions(mine, other)
        verdict = self._model_verdict(directions)
        allowed = self._compatibility.allows(directions) if verdict is None else verdict.allowed
        if not allowed:
            if verdict is not None:
                self._record_evaluation(
                    mine,
                    other,
                    verdict,
                    verdict.outcome or MatchEvaluationOutcome.SKIPPED_ERROR,
                )
            return False
        locked = self._lock_waiting(other.id, now)
        if locked is None:
            if verdict is not None:
                self._record_evaluation(mine, other, verdict, MatchEvaluationOutcome.SKIPPED_LOCK)
            return False
        claimed = self._claim_pair(mine, locked, now)
        if verdict is not None:
            self._record_evaluation(
                mine,
                other,
                verdict,
                MatchEvaluationOutcome.PAIRED if claimed else MatchEvaluationOutcome.SKIPPED_LOCK,
            )
        if claimed:
            self._clean_candidates(
                condition_ids=[mine.id, other.id],
                user_ids=[mine.user_id, other.user_id],
            )
        return claimed

    def _model_verdict(
        self,
        directions: tuple[DirectionInput, DirectionInput],
    ) -> CompatibilityVerdict | None:
        judge = getattr(self._compatibility, "judge", None)
        if not callable(judge):
            return None
        return judge(directions)

    def _pair_directions(
        self,
        mine: MatchCondition,
        other: MatchCondition,
    ) -> tuple[DirectionInput, DirectionInput]:
        mine_wants = StrengthTag(mine.want_tag)
        other_wants = StrengthTag(other.want_tag)
        return (
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

    def _record_evaluation(
        self,
        mine: MatchCondition,
        other: MatchCondition,
        verdict: CompatibilityVerdict,
        outcome: MatchEvaluationOutcome,
    ) -> None:
        try:
            with self._session.begin_nested():
                self._session.add(
                    MatchEvaluation(
                        condition_ids=sorted((mine.id, other.id), key=str),
                        sides=_evaluation_sides(mine, other, verdict),
                        outcome=outcome.value,
                        error_class=verdict.error_class
                        if outcome is MatchEvaluationOutcome.SKIPPED_ERROR
                        else None,
                    )
                )
                self._session.flush()
        except Exception:
            logger.warning("匹配决策留痕失败", exc_info=True)

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


def _evaluation_sides(
    mine: MatchCondition,
    other: MatchCondition,
    verdict: CompatibilityVerdict,
) -> dict[str, dict[str, object]]:
    by_direction = {item.direction_id: item for item in verdict.decisions}
    known = {mine.id, other.id}
    sides: dict[str, dict[str, object]] = {}
    for direction in verdict.directions:
        condition_id = _answerer_condition_id(direction.id, mine, other, known)
        decision = by_direction.get(direction.id)
        sides[str(condition_id)] = {
            "evidence": [
                {
                    "id": item.id,
                    "title": item.title,
                    "confidence": item.confidence,
                    "reason": item.reason,
                }
                for item in direction.candidate_evidence
            ],
            "decision": None
            if decision is None
            else {
                "signal": decision.signal,
                "confidence": decision.confidence,
                "reason": decision.reason,
                "evidence_ids": list(decision.evidence_ids),
            },
        }
    return sides


def _answerer_condition_id(
    direction_id: str,
    mine: MatchCondition,
    other: MatchCondition,
    known: set[uuid.UUID],
) -> uuid.UUID:
    question_id = direction_id.split(":", 1)[-1]
    if question_id == str(mine.id) and other.id in known:
        return other.id
    if question_id == str(other.id) and mine.id in known:
        return mine.id
    return other.id


def _capability_evidence_id(tag: StrengthTag, title: str, url: str) -> str:
    digest = sha256(f"{tag.value}\0{url}\0{title}".encode()).hexdigest()[:16]
    return f"portrait:{digest}"
