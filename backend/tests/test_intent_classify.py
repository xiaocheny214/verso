"""意图分类：叶子节点提示词、JSON 打分解析、失败降级。"""

from __future__ import annotations

import json
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from verso_app.server.intent.models import IntentNode
from verso_app.server.llm_pipeline.intent_classify import classify_targets
from verso_common.enums import IntentKind
from verso_framework.config.app import AppSettings


def _node(
    identifier: str,
    name: str,
    *,
    parent: IntentNode | None = None,
    kind: str = IntentKind.KB_RETRIEVE,
    description: str = "",
    examples: str = "",
    enabled: bool = True,
) -> IntentNode:
    return IntentNode(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        parent_id=parent.id if parent is not None else None,
        identifier=identifier,
        name=name,
        kind=kind,
        description=description,
        examples=examples,
        enabled=enabled,
    )


class _FakeModel:
    def __init__(self, payload: object) -> None:
        self.messages: list[object] = []
        self.bind_kwargs: dict[str, object] | None = None
        self._payload = payload

    def bind(self, **kwargs: object) -> _FakeModel:
        self.bind_kwargs = kwargs
        return self

    def invoke(self, messages: list[object]) -> AIMessage:
        self.messages.extend(messages)
        if isinstance(self._payload, Exception):
            raise self._payload
        if isinstance(self._payload, str):
            content = self._payload
        else:
            content = json.dumps(self._payload, ensure_ascii=False)
        return AIMessage(content=content)


def test_classify_targets_scores_leaves_and_renders_prompt() -> None:
    domain = _node("biz", "业务系统", description="业务域")
    oa = _node("biz_oa", "OA系统", parent=domain)
    intro = _node(
        "biz_oa_intro",
        "系统介绍",
        parent=oa,
        description="OA 系统整体功能",
        examples='["OA 有哪些功能", "介绍一下 OA"]',
    )
    security = _node(
        "biz_oa_security",
        "数据安全",
        parent=oa,
        description="OA 数据安全要求",
    )
    model = _FakeModel(
        [
            {"id": "biz_oa_security", "score": 0.91, "reason": "数据安全"},
            {"id": "biz_oa_intro", "score": 0.4, "reason": "系统介绍"},
            {"id": "missing", "score": 0.99, "reason": "不存在"},
            {"score": 0.5},
        ]
    )

    scores = classify_targets(
        "OA系统的数据安全要求",
        [domain, oa, intro, security],
        settings=AppSettings(),
        model=model,
    )

    assert [item.node.identifier for item in scores] == ["biz_oa_security", "biz_oa_intro"]
    assert [item.score for item in scores] == [0.91, 0.4]
    assert model.bind_kwargs == {"temperature": 0.1, "top_p": 0.3}
    system = next(message for message in model.messages if isinstance(message, SystemMessage))
    assert isinstance(system.content, str)
    assert "企业内部助手的意图分类器" in system.content
    assert "- id=biz_oa_intro" in system.content
    assert "path=业务系统 > OA系统 > 系统介绍" in system.content
    assert "type=KB" in system.content
    assert "examples=OA 有哪些功能 / 介绍一下 OA" in system.content
    assert "- id=biz\n" not in system.content
    assert "- id=biz_oa\n" not in system.content
    human = next(message for message in model.messages if isinstance(message, HumanMessage))
    assert human.content == "OA系统的数据安全要求"


def test_classify_targets_accepts_fenced_json_and_results_wrapper() -> None:
    leaf = _node("biz_oa_intro", "系统介绍")
    body = json.dumps(
        {"results": [{"id": "biz_oa_intro", "score": 0.88, "reason": "系统介绍"}]},
        ensure_ascii=False,
    )
    model = _FakeModel(f"```json\n{body}\n```")

    scores = classify_targets("介绍 OA", [leaf], settings=AppSettings(), model=model)

    assert len(scores) == 1
    assert scores[0].node.identifier == "biz_oa_intro"
    assert scores[0].score == 0.88


def test_classify_targets_returns_empty_when_model_fails() -> None:
    leaf = _node("biz_oa_intro", "系统介绍")
    model = _FakeModel(RuntimeError("timeout"))

    scores = classify_targets("介绍 OA", [leaf], settings=AppSettings(), model=model)

    assert scores == []


def test_classify_targets_returns_empty_on_malformed_json() -> None:
    leaf = _node("biz_oa_intro", "系统介绍")
    model = _FakeModel("不是 JSON")

    scores = classify_targets("介绍 OA", [leaf], settings=AppSettings(), model=model)

    assert scores == []


def test_classify_targets_skips_model_when_no_kb_leaf() -> None:
    parent = _node("biz", "业务系统")
    child = _node("sys_feedback", "反馈", parent=parent, kind="system")
    model = _FakeModel(RuntimeError("should not be called"))

    scores = classify_targets("你好", [parent, child], settings=AppSettings(), model=model)

    assert scores == []
    assert model.messages == []
