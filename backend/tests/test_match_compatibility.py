import json

import pytest

from verso_app.server.match.compatibility import (
    MAX_EVIDENCE_PER_DIRECTION,
    MIN_COMPATIBILITY_CONFIDENCE,
    CapabilityEvidence,
    DirectionInput,
    LlmPairCompatibilityEvaluator,
    SafePairCompatibilityEvaluator,
)
from verso_common.enums import StrengthTag


class _Message:
    def __init__(self, content) -> None:
        self.content = content


class _Structured:
    def __init__(self, response) -> None:
        self.response = response
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, str):
            return _Message(self.response)
        return self.response


class _Model:
    def __init__(self, response) -> None:
        self.response = response
        self.structured = None
        self.structured_schema = None
        self.structured_kwargs = None

    def with_structured_output(self, schema, **kwargs):
        self.structured_schema = schema
        self.structured_kwargs = kwargs
        self.structured = _Structured(self.response)
        return self.structured


def _direction(direction_id: str, *, evidence_count: int = 1) -> DirectionInput:
    return DirectionInput(
        id=direction_id,
        question="我正在养一棵两年咖啡树，根已长出盆底，什么时候换盆？",
        requested_tag=StrengthTag.OTHER,
        candidate_evidence=tuple(
            CapabilityEvidence(
                id=f"evidence-{direction_id}-{index}",
                title=f"盆栽咖啡换盆复盘 {index}",
                url=f"https://example.test/{direction_id}/{index}",
                reason="记录根系状态、盆径和换盆后的恢复情况",
                confidence=90,
            )
            for index in range(evidence_count)
        ),
    )


def _supported(direction: DirectionInput, *, confidence: int = 90) -> dict:
    return {
        "direction_id": direction.id,
        "signal": "supported",
        "confidence": confidence,
        "evidence_ids": [direction.candidate_evidence[0].id],
        "reason": "问题与候选人的换盆实践直接相关",
    }


def test_llm_requires_both_directions_to_be_supported() -> None:
    left = _direction("left")
    right = _direction("right")
    model = _Model({"directions": [_supported(left), _supported(right)]})

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True


@pytest.mark.parametrize("signal", ["unsupported", "unclear"])
def test_llm_rejects_a_non_supported_direction(signal: str) -> None:
    left = _direction("left")
    right = _direction("right")
    rejected = _supported(right)
    rejected["signal"] = signal
    rejected["evidence_ids"] = []
    model = _Model({"directions": [_supported(left), rejected]})

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is False


def test_llm_rejects_low_confidence_even_when_signal_is_supported() -> None:
    left = _direction("left")
    right = _direction("right")
    model = _Model(
        {
            "directions": [
                _supported(left),
                _supported(right, confidence=MIN_COMPATIBILITY_CONFIDENCE - 1),
            ]
        }
    )

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is False


def test_llm_rejects_unknown_evidence_reference() -> None:
    left = _direction("left")
    right = _direction("right")
    invalid = _supported(right)
    invalid["evidence_ids"] = ["unknown"]
    model = _Model({"directions": [_supported(left), invalid]})

    with pytest.raises(ValueError, match="evidence ids"):
        LlmPairCompatibilityEvaluator(model).allows((left, right))


def test_safe_evaluator_skips_candidate_when_model_fails() -> None:
    evaluator = SafePairCompatibilityEvaluator(
        LlmPairCompatibilityEvaluator(_Model(RuntimeError("model down")))
    )

    assert evaluator.allows((_direction("left"), _direction("right"))) is False


def test_llm_input_limits_evidence_and_omits_urls() -> None:
    left = _direction("left", evidence_count=MAX_EVIDENCE_PER_DIRECTION + 2)
    right = _direction("right")
    model = _Model({"directions": [_supported(left), _supported(right)]})

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True
    payload = json.loads(model.structured.messages[1].content)
    assert len(payload["directions"][0]["candidate_evidence"]) == MAX_EVIDENCE_PER_DIRECTION
    assert all(
        "url" not in evidence
        for direction in payload["directions"]
        for evidence in direction["candidate_evidence"]
    )


def test_llm_uses_json_mode_schema() -> None:
    left = _direction("left")
    right = _direction("right")
    model = _Model({"directions": [_supported(left), _supported(right)]})

    LlmPairCompatibilityEvaluator(model).allows((left, right))

    assert isinstance(model.structured_schema, dict)
    assert model.structured_kwargs["method"] == "json_mode"
    assert model.structured_kwargs["include_raw"] is True
    assert model.structured_schema["properties"]["directions"]["items"]["required"] == [
        "direction_id",
        "signal",
        "confidence",
        "evidence_ids",
        "reason",
    ]


def test_llm_parses_fenced_json_array() -> None:
    left = _direction("left")
    right = _direction("right")
    fenced = (
        "```json\n"
        + json.dumps([_supported(left), _supported(right)], ensure_ascii=False, indent=2)
        + "\n```"
    )
    model = _Model(fenced)

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True


def test_llm_parses_fenced_json_object() -> None:
    left = _direction("left")
    right = _direction("right")
    fenced = (
        "```json\n"
        + json.dumps(
            {"directions": [_supported(left), _supported(right)]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n```"
    )
    model = _Model(fenced)

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True


def test_llm_parses_bare_json_array() -> None:
    left = _direction("left")
    right = _direction("right")
    model = _Model(json.dumps([_supported(left), _supported(right)], ensure_ascii=False))

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True


def test_llm_uses_json_mode_parsed_dict() -> None:
    left = _direction("left")
    right = _direction("right")
    model = _Model(
        {
            "raw": _Message("ignored"),
            "parsed": {"directions": [_supported(left), _supported(right)]},
            "parsing_error": None,
        }
    )

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True


def test_llm_recovers_raw_when_json_mode_parse_fails() -> None:
    left = _direction("left")
    right = _direction("right")
    fenced = (
        "```json\n"
        + json.dumps([_supported(left), _supported(right)], ensure_ascii=False, indent=2)
        + "\n```"
    )
    model = _Model(
        {
            "raw": _Message(fenced),
            "parsed": None,
            "parsing_error": ValueError("not json"),
        }
    )

    assert LlmPairCompatibilityEvaluator(model).allows((left, right)) is True
