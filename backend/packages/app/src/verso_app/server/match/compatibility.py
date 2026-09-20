"""用具体问题与画像证据校验双向互补，不负责创建配对。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeGuard

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from verso_common.enums import MatchEvaluationOutcome, StrengthTag
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


@dataclass(frozen=True, slots=True)
class RecordedDirectionDecision:
    direction_id: str
    signal: str
    confidence: int
    reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompatibilityVerdict:
    """模型看过这一对之后的结论。allowed 仍决定能否配对。"""

    allowed: bool
    outcome: MatchEvaluationOutcome | None
    error_class: str | None
    decisions: tuple[RecordedDirectionDecision, ...]
    directions: tuple[DirectionInput, ...]


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


def _strip_code_fences(text: str) -> str:
    """Remove ```json ...``` style fences and surrounding prose from model output."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        body = stripped[first_newline + 1 :] if first_newline != -1 else stripped[3:]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
        return body.strip()
    return stripped


def _message_payload(raw: object) -> object:
    """Read LangChain message content without using OpenAI native parse."""
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    return content


def _parse_llm_pair(raw: object) -> _LlmPairDecision:
    """Validate JSON as `_LlmPairDecision` after stripping common provider wrappers."""
    if isinstance(raw, _LlmPairDecision):
        return raw
    payload = _message_payload(raw)
    if isinstance(payload, str):
        payload = json.loads(_strip_code_fences(payload))
    if isinstance(payload, list):
        return _LlmPairDecision.model_validate({"directions": payload})
    return _LlmPairDecision.model_validate(payload)


def _is_include_raw_payload(raw: object) -> TypeGuard[dict]:
    return (
        isinstance(raw, dict)
        and "raw" in raw
        and ("parsed" in raw or "parsing_error" in raw)
        and "directions" not in raw
    )


def _parse_structured_pair(raw: object) -> _LlmPairDecision:
    """Use json_mode's parsed dict when present; otherwise recover from the raw message."""
    if not _is_include_raw_payload(raw):
        return _parse_llm_pair(raw)
    parsed = raw.get("parsed")
    if parsed is not None:
        return _parse_llm_pair(parsed)
    return _parse_llm_pair(raw.get("raw"))


_LLM_PAIR_JSON_SCHEMA: dict[str, object] = {
    "title": "LlmPairDecision",
    "type": "object",
    "properties": {
        "directions": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
                "type": "object",
                "properties": {
                    "direction_id": {"type": "string"},
                    "signal": {
                        "type": "string",
                        "enum": [item.value for item in CompatibilitySignal],
                    },
                    "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                    "evidence_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 3,
                    },
                    "reason": {"type": "string"},
                },
                "required": [
                    "direction_id",
                    "signal",
                    "confidence",
                    "evidence_ids",
                    "reason",
                ],
            },
        }
    },
    "required": ["directions"],
}

_SYSTEM_PROMPT = """你是 Verso 的双向匹配证据校验器。你只判断候选人的已有实践证据，能否支持他回答这个具体问题。

逐个方向判断：
- supported：问题需要结合具体情况、实践经验或后续追问，并且候选证据与这个具体问题直接相关。
- unsupported：证据属于同一个大类，但具体经历不相关；或者问题只是搜索/AI即可直接回答的通用事实。
- unclear：问题太宽泛、缺少背景，或证据不足以判断。

不得从大类标签推测候选人会做未被证据支持的事情。supported 必须引用至少一个输入中的 evidence_id；不得引用未知证据。每个 direction_id 必须且只能返回一次。不要回答用户的问题，只输出 JSON，不要用 markdown 代码块包裹。形状必须是：
{"directions":[{"direction_id":"...","signal":"supported","confidence":85,"evidence_ids":["..."],"reason":"..."},{"direction_id":"...","signal":"supported","confidence":85,"evidence_ids":["..."],"reason":"..."}]}
"""


class LlmPairCompatibilityEvaluator:
    def __init__(self, model: BaseChatModel) -> None:
        self._structured = model.with_structured_output(
            _LLM_PAIR_JSON_SCHEMA,
            method="json_mode",
            include_raw=True,
        )

    def allows(self, directions: tuple[DirectionInput, DirectionInput]) -> bool:
        return self.judge(directions).allowed

    def judge(self, directions: tuple[DirectionInput, DirectionInput]) -> CompatibilityVerdict:
        bounded = _bound_directions(directions)
        payload = [
            {
                "direction_id": item.id,
                "question": item.question,
                "requested_tag": item.requested_tag.value,
                "candidate_evidence": [
                    {
                        "evidence_id": evidence.id,
                        "title": evidence.title,
                        "reason": evidence.reason,
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
        parsed = _parse_structured_pair(raw)
        recorded = tuple(_recorded(item) for item in parsed.directions)
        allowed = _both_directions_supported(bounded, parsed.directions)
        return CompatibilityVerdict(
            allowed=allowed,
            outcome=None if allowed else _skip_outcome(parsed.directions),
            error_class=None,
            decisions=recorded,
            directions=bounded,
        )


class SafePairCompatibilityEvaluator:
    """模型异常时跳过候选，不能退回一次无证据的成功匹配。"""

    def __init__(self, primary: PairCompatibilityEvaluator) -> None:
        self._primary = primary

    def allows(self, directions: tuple[DirectionInput, DirectionInput]) -> bool:
        return self.judge(directions).allowed

    def judge(self, directions: tuple[DirectionInput, DirectionInput]) -> CompatibilityVerdict:
        judge = getattr(self._primary, "judge", None)
        try:
            if callable(judge):
                return judge(directions)
            allowed = self._primary.allows(directions)
        except Exception as exc:
            logger.warning("具体问题匹配判断失败，跳过候选", exc_info=True)
            return CompatibilityVerdict(
                allowed=False,
                outcome=MatchEvaluationOutcome.SKIPPED_ERROR,
                error_class=type(exc).__name__,
                decisions=(),
                directions=_bound_directions(directions),
            )
        return CompatibilityVerdict(
            allowed=allowed,
            outcome=None if allowed else MatchEvaluationOutcome.SKIPPED_UNSUPPORTED,
            error_class=None,
            decisions=(),
            directions=_bound_directions(directions),
        )


def build_pair_compatibility_evaluator(settings: AppSettings) -> PairCompatibilityEvaluator:
    if not settings.llm_api_key or not settings.llm_model:
        return TagOnlyCompatibilityEvaluator()
    return SafePairCompatibilityEvaluator(LlmPairCompatibilityEvaluator(build_chat_model(settings)))


def _bound_directions(
    directions: tuple[DirectionInput, DirectionInput],
) -> tuple[DirectionInput, DirectionInput]:
    return tuple(
        DirectionInput(
            id=item.id,
            question=item.question[:500],
            requested_tag=item.requested_tag,
            candidate_evidence=tuple(
                CapabilityEvidence(
                    id=evidence.id,
                    title=evidence.title[:240],
                    url=evidence.url,
                    reason=evidence.reason[:160],
                    confidence=evidence.confidence,
                )
                for evidence in item.candidate_evidence[:MAX_EVIDENCE_PER_DIRECTION]
            ),
        )
        for item in directions
    )


def _recorded(decision: _LlmDirectionDecision) -> RecordedDirectionDecision:
    return RecordedDirectionDecision(
        direction_id=decision.direction_id,
        signal=decision.signal.value,
        confidence=decision.confidence,
        reason=decision.reason,
        evidence_ids=tuple(decision.evidence_ids),
    )


def _skip_outcome(decisions: list[_LlmDirectionDecision]) -> MatchEvaluationOutcome:
    if any(item.signal is CompatibilitySignal.UNSUPPORTED for item in decisions):
        return MatchEvaluationOutcome.SKIPPED_UNSUPPORTED
    if any(item.signal is CompatibilitySignal.UNCLEAR for item in decisions):
        return MatchEvaluationOutcome.SKIPPED_UNCLEAR
    return MatchEvaluationOutcome.SKIPPED_LOW_CONFIDENCE


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
