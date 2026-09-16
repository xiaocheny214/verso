import json
from datetime import UTC, datetime, timedelta

import pytest

from verso_app.server.portrait.extractor import (
    EvidenceAssessment,
    EvidenceInput,
    EvidenceKind,
    EvidenceSignal,
    FallbackEvidenceClassifier,
    LlmEvidenceClassifier,
    RuleEvidenceClassifier,
    aggregate_portrait,
)
from verso_common.enums import StrengthTag


def _evidence(
    evidence_id: str,
    *,
    kind: EvidenceKind = EvidenceKind.CONTENT,
    title: str = "Python 后端性能优化复盘",
    days_ago: int = 1,
) -> EvidenceInput:
    return EvidenceInput(
        id=evidence_id,
        kind=kind,
        content_type="article",
        title=title,
        text="记录线上问题、分析过程和最终修复。",
        url=f"https://example.test/{evidence_id}",
        observed_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


def test_rules_treat_saved_topic_as_interest_not_skill() -> None:
    item = _evidence(
        "favorite-1",
        kind=EvidenceKind.FAVORITE,
        title="徒手健身入门",
    )
    decision = RuleEvidenceClassifier().classify([item])[0]
    assert decision.tags == (StrengthTag.FITNESS,)
    assert decision.signal == EvidenceSignal.INTEREST_ONLY
    assert aggregate_portrait([item], [decision]).tags == []


def test_rules_do_not_turn_question_or_negative_statement_into_skill() -> None:
    questions = [
        _evidence("q1", title="零基础怎么学 Python？"),
        EvidenceInput(
            id="q2",
            kind=EvidenceKind.CONTENT,
            content_type="article",
            title="转行记录",
            text="我不会写代码，想学 Python。",
            url="https://example.test/q2",
            observed_at=datetime.now(UTC),
        ),
    ]
    decisions = RuleEvidenceClassifier().classify(questions)
    assert all(item.signal == EvidenceSignal.UNCLEAR for item in decisions)
    assert aggregate_portrait(questions, decisions).tags == []


def test_rules_do_not_treat_a_question_object_as_skill() -> None:
    item = EvidenceInput(
        id="question",
        kind=EvidenceKind.CONTENT,
        content_type="question",
        title="Python 性能优化",
        text="如何定位线上延迟？",
        url="https://example.test/question",
        observed_at=datetime.now(UTC),
    )

    decision = RuleEvidenceClassifier().classify([item])[0]

    assert decision.signal == EvidenceSignal.UNCLEAR


def test_rules_require_more_than_a_topic_mention() -> None:
    item = EvidenceInput(
        id="mention",
        kind=EvidenceKind.CONTENT,
        content_type="article",
        title="聊聊 Python",
        text="一些想法。",
        url="https://example.test/mention",
        observed_at=datetime.now(UTC),
    )

    decision = RuleEvidenceClassifier().classify([item])[0]

    assert decision.signal == EvidenceSignal.UNCLEAR


def test_aggregation_does_not_trust_skill_claims_for_favorites() -> None:
    item = _evidence("favorite", kind=EvidenceKind.FAVORITE, title="徒手健身教程")
    incorrect = EvidenceAssessment(
        evidence_id=item.id,
        tags=(StrengthTag.FITNESS,),
        signal=EvidenceSignal.DEMONSTRATES_SKILL,
        confidence=100,
        reason="错误分类",
        extractor="bad-classifier",
    )

    assert aggregate_portrait([item], [incorrect]).tags == []


def test_aggregation_is_deterministic_and_maps_representative_evidence() -> None:
    older = _evidence("older", days_ago=30)
    recent = _evidence("recent", days_ago=1)
    assessments = [
        EvidenceAssessment(
            evidence_id="older",
            tags=(StrengthTag.PROGRAMMING,),
            signal=EvidenceSignal.DEMONSTRATES_SKILL,
            confidence=90,
            reason="有完整实践复盘",
            extractor="fake-v1",
        ),
        EvidenceAssessment(
            evidence_id="recent",
            tags=(StrengthTag.PROGRAMMING,),
            signal=EvidenceSignal.DEMONSTRATES_SKILL,
            confidence=90,
            reason="有完整实践复盘",
            extractor="fake-v1",
        ),
    ]
    result = aggregate_portrait([older, recent], assessments)
    assert result.tags == [StrengthTag.PROGRAMMING]
    assert result.evidence[0]["title"] == recent.title
    assert result.evidence[0]["extractor"] == "fake-v1"


def test_recent_portrait_reuses_decisions_and_filters_by_time() -> None:
    old = _evidence("old", days_ago=30)
    recent = _evidence("recent", title="徒手健身训练复盘", days_ago=1)
    assessments = [
        EvidenceAssessment(
            evidence_id="old",
            tags=(StrengthTag.PROGRAMMING,),
            signal=EvidenceSignal.DEMONSTRATES_SKILL,
            confidence=90,
            reason="实践复盘",
            extractor="fake-v1",
        ),
        EvidenceAssessment(
            evidence_id="recent",
            tags=(StrengthTag.FITNESS,),
            signal=EvidenceSignal.DEMONSTRATES_SKILL,
            confidence=90,
            reason="训练复盘",
            extractor="fake-v1",
        ),
    ]
    result = aggregate_portrait(
        [old, recent],
        assessments,
        since=datetime.now(UTC) - timedelta(days=7),
    )
    assert result.tags == [StrengthTag.FITNESS]


class _Message:
    def __init__(self, content) -> None:
        self.content = content


class _Model:
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


def test_llm_classifier_rejects_missing_or_unknown_evidence_ids() -> None:
    classifier = LlmEvidenceClassifier(
        _Model(
            {
                "decisions": [
                    {
                        "evidence_id": "unknown",
                        "tags": ["编程"],
                        "signal": "demonstrates_skill",
                        "confidence": 95,
                        "reason": "实践复盘",
                    }
                ]
            }
        )
    )
    with pytest.raises(ValueError, match="evidence ids"):
        classifier.classify([_evidence("expected")])


def test_model_failure_falls_back_to_conservative_rules() -> None:
    classifier = FallbackEvidenceClassifier(
        LlmEvidenceClassifier(_Model(RuntimeError("model down"))),
        RuleEvidenceClassifier(),
    )
    item = _evidence("saved", kind=EvidenceKind.FAVORITE, title="Python 教程")
    decision = classifier.classify([item])[0]
    assert decision.extractor == "rule-v2"
    assert decision.signal == EvidenceSignal.INTEREST_ONLY


def test_llm_only_receives_authored_content() -> None:
    authored = _evidence("post")
    saved = _evidence("saved", kind=EvidenceKind.FAVORITE, title="徒手健身入门")
    model = _Model(
        {
            "decisions": [
                {
                    "evidence_id": "post",
                    "tags": ["编程"],
                    "signal": "demonstrates_skill",
                    "confidence": 92,
                    "reason": "包含实践过程",
                }
            ]
        }
    )

    decisions = LlmEvidenceClassifier(model).classify([authored, saved])

    assert [item.evidence_id for item in decisions] == ["post", "saved"]
    assert decisions[1].signal == EvidenceSignal.INTEREST_ONLY
    payload = json.loads(model.messages[1].content)
    assert [item["evidence_id"] for item in payload["evidence"]] == ["post"]


def test_llm_input_is_bounded_and_older_content_uses_rules() -> None:
    evidence = [_evidence(f"post-{index}", days_ago=index) for index in range(25)]
    model = _Model(
        {
            "decisions": [
                {
                    "evidence_id": f"post-{index}",
                    "tags": ["编程"],
                    "signal": "demonstrates_skill",
                    "confidence": 90,
                    "reason": "包含实践过程",
                }
                for index in range(24)
            ]
        }
    )

    decisions = LlmEvidenceClassifier(model).classify(evidence)

    payload = json.loads(model.messages[1].content)
    assert len(payload["evidence"]) == 24
    assert decisions[-1].extractor == "rule-v2"


def test_llm_classifier_parses_fenced_json_array() -> None:
    fenced = (
        "```json\n"
        '[\n  {\n    "evidence_id": "post",\n    "tags": ["编程"],\n'
        '    "signal": "demonstrates_skill",\n    "confidence": 92,\n'
        '    "reason": "包含实践过程"\n  }\n]\n'
        "```"
    )
    classifier = LlmEvidenceClassifier(_Model(fenced))
    decisions = classifier.classify([_evidence("post")])

    assert [item.evidence_id for item in decisions] == ["post"]
    assert decisions[0].extractor == "llm-v1"
    assert decisions[0].tags == (StrengthTag.PROGRAMMING,)


def test_llm_classifier_parses_fenced_json_object() -> None:
    fenced = (
        "```json\n"
        '{\n  "decisions": [\n    {\n      "evidence_id": "post",\n'
        '      "tags": ["编程"],\n      "signal": "demonstrates_skill",\n'
        '      "confidence": 92,\n      "reason": "包含实践过程"\n    }\n  ]\n}\n'
        "```"
    )
    classifier = LlmEvidenceClassifier(_Model(fenced))
    decisions = classifier.classify([_evidence("post")])

    assert decisions[0].extractor == "llm-v1"
    assert decisions[0].tags == (StrengthTag.PROGRAMMING,)


def test_llm_classifier_parses_bare_json_array() -> None:
    bare = (
        '[\n  {\n    "evidence_id": "post",\n    "tags": ["编程"],\n'
        '    "signal": "demonstrates_skill",\n    "confidence": 92,\n'
        '    "reason": "包含实践过程"\n  }\n]'
    )
    classifier = LlmEvidenceClassifier(_Model(bare))
    decisions = classifier.classify([_evidence("post")])

    assert decisions[0].extractor == "llm-v1"
    assert decisions[0].tags == (StrengthTag.PROGRAMMING,)
