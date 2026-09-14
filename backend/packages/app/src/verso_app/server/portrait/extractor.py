"""Evidence-first portrait extraction.

Models may classify evidence, but deterministic domain rules own promotion into a
matchable strength. Interest signals never become skills by themselves.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from verso_app.server.portrait.tagger import tags_from_text
from verso_common.enums import PortraitSource, StrengthTag
from verso_framework.config.app import AppSettings
from verso_framework.providers.llm import build_chat_model

MAX_STRENGTHS = 3
MIN_SKILL_CONFIDENCE = 70
MAX_LLM_CONTENTS = 24

logger = logging.getLogger("verso.portrait.extractor")


class EvidenceKind(StrEnum):
    CONTENT = "content"
    FAVORITE = "favorite"
    FOLLOWEE = "followee"


class EvidenceSignal(StrEnum):
    DEMONSTRATES_SKILL = "demonstrates_skill"
    INTEREST_ONLY = "interest_only"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    id: str
    kind: EvidenceKind
    content_type: str
    title: str
    text: str
    url: str
    observed_at: datetime | None


@dataclass(frozen=True, slots=True)
class EvidenceAssessment:
    evidence_id: str
    tags: tuple[StrengthTag, ...]
    signal: EvidenceSignal
    confidence: int
    reason: str
    extractor: str


@dataclass(frozen=True, slots=True)
class AggregatedPortrait:
    tags: list[StrengthTag]
    evidence: list[dict[str, object]]
    source: PortraitSource


class EvidenceClassifier(Protocol):
    def classify(self, evidence: list[EvidenceInput]) -> list[EvidenceAssessment]: ...


_NON_SKILL_PHRASES = (
    "我不会",
    "我不懂",
    "零基础怎么",
    "求助",
    "请问",
    "想学",
    "想了解",
)
_SKILL_EVIDENCE_PHRASES = (
    "教程",
    "复盘",
    "指南",
    "经验",
    "实战",
    "实践",
    "详解",
    "笔记",
    "训练",
    "入门",
    "开发",
    "实现",
    "分析",
    "总结",
    "解决",
)


class RuleEvidenceClassifier:
    """Offline fallback that deliberately prefers false negatives."""

    version = "rule-v2"

    def classify(self, evidence: list[EvidenceInput]) -> list[EvidenceAssessment]:
        decisions: list[EvidenceAssessment] = []
        for item in evidence:
            tags = tuple(tags_from_text(item.title, item.text))
            blob = f"{item.title} {item.text}".lower()
            if not tags:
                signal = EvidenceSignal.UNCLEAR
                confidence = 0
                reason = "规则未命中闭集标签"
            elif item.kind is not EvidenceKind.CONTENT:
                signal = EvidenceSignal.INTEREST_ONLY
                confidence = 80
                reason = "收藏或关注只能证明兴趣，不能单独证明能教"
            elif item.content_type.lower() == "question" or any(
                phrase in blob for phrase in _NON_SKILL_PHRASES
            ):
                signal = EvidenceSignal.UNCLEAR
                confidence = 40
                reason = "文本更像提问或自述不会，不能证明能力"
            elif not any(phrase in blob for phrase in _SKILL_EVIDENCE_PHRASES):
                signal = EvidenceSignal.UNCLEAR
                confidence = 50
                reason = "单次领域词不足以证明能够讲解或分享实践"
            else:
                signal = EvidenceSignal.DEMONSTRATES_SKILL
                confidence = MIN_SKILL_CONFIDENCE
                reason = "本人创作命中闭集能力词"
            decisions.append(
                EvidenceAssessment(
                    evidence_id=item.id,
                    tags=tags,
                    signal=signal,
                    confidence=confidence,
                    reason=reason,
                    extractor=self.version,
                )
            )
        return decisions


class _LlmDecision(BaseModel):
    evidence_id: str
    tags: list[StrengthTag] = Field(default_factory=list, max_length=3)
    signal: EvidenceSignal
    confidence: int = Field(ge=0, le=100)
    reason: str = Field(min_length=1, max_length=160)


class _LlmBatch(BaseModel):
    decisions: list[_LlmDecision]


_SYSTEM_PROMPT = """你是 Verso 的能力证据分类器。你的任务不是描述人格，而是判断每条知乎证据能否证明用户有能力教别人。

约束：
- tags 只能从给定闭集选择，最多 3 个；没有合适标签就返回空列表。
- 本人创作的教程、复盘、解释或实践经验可以是 demonstrates_skill。
- 提问、表达想学、表达不会，只能是 unclear，不能因为包含领域词就算能力。
- 收藏别人的内容、关注某个人只证明 interest_only，绝不能单独判为 demonstrates_skill。
- 证据不足时选择 unclear；不要猜测。
- confidence 表示这条证据支持当前 signal 和 tags 的把握，不表示用户人格分数。
- 每个 evidence_id 必须且只能返回一次。
"""


class LlmEvidenceClassifier:
    version = "llm-v1"

    def __init__(self, model: BaseChatModel) -> None:
        self._structured = model.with_structured_output(_LlmBatch)
        self._rules = RuleEvidenceClassifier()

    def classify(self, evidence: list[EvidenceInput]) -> list[EvidenceAssessment]:
        if not evidence:
            return []
        authored = sorted(
            (item for item in evidence if item.kind is EvidenceKind.CONTENT),
            key=lambda item: (
                -(item.observed_at.timestamp() if item.observed_at else 0),
                item.id,
            ),
        )[:MAX_LLM_CONTENTS]
        delegated_ids = {item.id for item in authored}
        fixed = self._rules.classify([item for item in evidence if item.id not in delegated_ids])
        if not authored:
            return fixed
        allowed = [tag.value for tag in StrengthTag if tag is not StrengthTag.OTHER]
        payload = [
            {
                "evidence_id": item.id,
                "source": item.kind.value,
                "content_type": item.content_type,
                "title": item.title[:240],
                "text": item.text[:800],
            }
            for item in authored
        ]
        raw = self._structured.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(
                    content=json.dumps(
                        {"allowed_tags": allowed, "evidence": payload},
                        ensure_ascii=False,
                    )
                ),
            ]
        )
        parsed = raw if isinstance(raw, _LlmBatch) else _LlmBatch.model_validate(raw)
        expected = delegated_ids
        returned = [item.evidence_id for item in parsed.decisions]
        if len(returned) != len(set(returned)) or set(returned) != expected:
            raise ValueError("LLM evidence ids do not match the request")
        model_decisions = [
            EvidenceAssessment(
                evidence_id=item.evidence_id,
                tags=tuple(item.tags),
                signal=item.signal,
                confidence=item.confidence,
                reason=item.reason,
                extractor=self.version,
            )
            for item in parsed.decisions
        ]
        by_id = {item.evidence_id: item for item in [*fixed, *model_decisions]}
        return [by_id[item.id] for item in evidence]


class FallbackEvidenceClassifier:
    def __init__(
        self,
        primary: EvidenceClassifier,
        fallback: EvidenceClassifier,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    def classify(self, evidence: list[EvidenceInput]) -> list[EvidenceAssessment]:
        try:
            return self._primary.classify(evidence)
        except Exception:
            logger.warning("画像 LLM 分类失败，使用保守规则", exc_info=True)
            return self._fallback.classify(evidence)


def build_evidence_classifier(settings: AppSettings) -> EvidenceClassifier:
    rules = RuleEvidenceClassifier()
    if settings.llm_api_key and settings.llm_model:
        return FallbackEvidenceClassifier(
            LlmEvidenceClassifier(build_chat_model(settings)),
            rules,
        )
    return rules


def aggregate_portrait(
    evidence: list[EvidenceInput],
    assessments: list[EvidenceAssessment],
    *,
    since: datetime | None = None,
) -> AggregatedPortrait:
    by_id = {item.id: item for item in evidence}
    eligible: dict[StrengthTag, list[tuple[EvidenceInput, EvidenceAssessment]]] = {}
    seen_evidence: set[str] = set()
    for assessment in assessments:
        if assessment.evidence_id in seen_evidence:
            continue
        seen_evidence.add(assessment.evidence_id)
        item = by_id.get(assessment.evidence_id)
        if item is None:
            continue
        if item.kind is not EvidenceKind.CONTENT:
            continue
        if item.content_type.lower() == "question":
            continue
        if since is not None and (item.observed_at is None or item.observed_at < since):
            continue
        if assessment.signal is not EvidenceSignal.DEMONSTRATES_SKILL:
            continue
        if assessment.confidence < MIN_SKILL_CONFIDENCE:
            continue
        for tag in assessment.tags:
            if tag is StrengthTag.OTHER:
                continue
            eligible.setdefault(tag, []).append((item, assessment))

    ranked = sorted(
        eligible,
        key=lambda tag: (
            -sum(decision.confidence for _, decision in eligible[tag]),
            -len(eligible[tag]),
            tag.value,
        ),
    )[:MAX_STRENGTHS]
    stored: list[dict[str, object]] = []
    for tag in ranked:
        candidates = sorted(
            eligible[tag],
            key=lambda pair: (
                -pair[1].confidence,
                -(pair[0].observed_at.timestamp() if pair[0].observed_at else 0),
                pair[0].id,
            ),
        )
        item, decision = candidates[0]
        stored.append(
            {
                "tag": tag.value,
                "source": PortraitSource.CONTENTS.value,
                "signal": decision.signal.value,
                "confidence": decision.confidence,
                "title": item.title,
                "url": item.url,
                "observed_at": item.observed_at.isoformat() if item.observed_at else None,
                "reason": decision.reason,
                "extractor": decision.extractor,
            }
        )
    return AggregatedPortrait(
        tags=ranked,
        evidence=stored,
        source=PortraitSource.CONTENTS,
    )
