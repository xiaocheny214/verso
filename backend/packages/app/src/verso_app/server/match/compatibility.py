"""用具体问题与画像证据校验双向互补，不负责创建配对。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from verso_common.enums import StrengthTag
from verso_framework.config.app import AppSettings
from verso_framework.providers.llm import build_chat_model

MAX_COMPATIBILITY_CANDIDATES = 5
MAX_EVIDENCE_PER_DIRECTION = 5
MIN_COMPATIBILITY_CONFIDENCE = 70

logger = logging.getLogger("verso.match.compatibility")


class CompatibilitySignal(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNCLEAR = "unclear"


@dataclass(frozen=True, slots=True)
class CapabilityEvidence:
    id: str
    title: str
    url: str
    reason: str
    confidence: int


@dataclass(frozen=True, slots=True)
class DirectionInput:
    id: str
    question: str
    requested_tag: StrengthTag
    candidate_evidence: tuple[CapabilityEvidence, ...]


class PairCompatibilityEvaluator(Protocol):
    def allows(self, directions: tuple[DirectionInput, DirectionInput]) -> bool: ...


class TagOnlyCompatibilityEvaluator:
    """模型未配置时保持现有大类双向覆盖行为。"""

    def allows(self, directions: tuple[DirectionInput, DirectionInput]) -> bool:
        return len(directions) == 2


class _LlmDirectionDecision(BaseModel):
    direction_id: str
    signal: CompatibilitySignal
    confidence: int = Field(ge=0, le=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=3)
    reason: str = Field(min_length=1, max_length=160)


class _LlmPairDecision(BaseModel):
    directions: list[_LlmDirectionDecision] = Field(min_length=2, max_length=2)


_SYSTEM_PROMPT = """你是 Verso 的双向匹配证据校验器。你只判断候选人的已有实践证据，能否支持他回答这个具体问题。

逐个方向判断：
- supported：问题需要结合具体情况、实践经验或后续追问，并且候选证据与这个具体问题直接相关。
- unsupported：证据属于同一个大类，但具体经历不相关；或者问题只是搜索/AI即可直接回答的通用事实。
- unclear：问题太宽泛、缺少背景，或证据不足以判断。

不得从大类标签推测候选人会做未被证据支持的事情。supported 必须引用至少一个输入中的 evidence_id；不得引用未知证据。每个 direction_id 必须且只能返回一次。不要回答用户的问题，只输出结构化判断。
"""


class LlmPairCompatibilityEvaluator:
    def __init__(self, model: BaseChatModel) -> None:
        self._structured = model.with_structured_output(_LlmPairDecision)

    def allows(self, directions: tuple[DirectionInput, DirectionInput]) -> bool:
        bounded = tuple(
            DirectionInput(
                id=item.id,
                question=item.question[:500],
                requested_tag=item.requested_tag,
                candidate_evidence=item.candidate_evidence[:MAX_EVIDENCE_PER_DIRECTION],
            )
            for item in directions
        )
        payload = [
            {
                "direction_id": item.id,
                "question": item.question,
                "requested_tag": item.requested_tag.value,
                "candidate_evidence": [
                    {
                        "evidence_id": evidence.id,
                        "title": evidence.title[:240],
                        "reason": evidence.reason[:160],
                        "confidence": evidence.confidence,
                    }
                    for evidence in item.candidate_evidence
                ],
            }
            for item in bounded
        ]
        raw = self._structured.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=json.dumps({"directions": payload}, ensure_ascii=False)),
            ]
        )
        parsed = raw if isinstance(raw, _LlmPairDecision) else _LlmPairDecision.model_validate(raw)
        return _both_directions_supported(bounded, parsed.directions)


class SafePairCompatibilityEvaluator:
    """模型异常时跳过候选，不能退回一次无证据的成功匹配。"""

    def __init__(self, primary: PairCompatibilityEvaluator) -> None:
        self._primary = primary

    def allows(self, directions: tuple[DirectionInput, DirectionInput]) -> bool:
        try:
            return self._primary.allows(directions)
        except Exception:
            logger.warning("具体问题匹配判断失败，跳过候选", exc_info=True)
            return False


def build_pair_compatibility_evaluator(settings: AppSettings) -> PairCompatibilityEvaluator:
    if not settings.llm_api_key or not settings.llm_model:
        return TagOnlyCompatibilityEvaluator()
    return SafePairCompatibilityEvaluator(LlmPairCompatibilityEvaluator(build_chat_model(settings)))


def _both_directions_supported(
    directions: tuple[DirectionInput, DirectionInput],
    decisions: list[_LlmDirectionDecision],
) -> bool:
    expected = {item.id: item for item in directions}
    returned = [item.direction_id for item in decisions]
    if len(returned) != len(set(returned)) or set(returned) != set(expected):
        raise ValueError("LLM direction ids do not match the request")
    for decision in decisions:
        direction = expected[decision.direction_id]
        known_evidence = {item.id for item in direction.candidate_evidence}
        if not set(decision.evidence_ids) <= known_evidence:
            raise ValueError("LLM cited unknown evidence ids")
        if decision.signal is not CompatibilitySignal.SUPPORTED:
            return False
        if not decision.evidence_ids:
            raise ValueError("LLM supported a direction without evidence ids")
        if decision.confidence < MIN_COMPATIBILITY_CONFIDENCE:
            return False
    return True
