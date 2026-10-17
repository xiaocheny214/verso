"""RAG 管道与查询改写。"""

from __future__ import annotations

import asyncio
import json
import uuid

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from verso_app.server.intent.models import IntentNode
from verso_app.server.retrieve import (
    KnowledgeRetrieveContext,
    MatchRetrieveContext,
    NodeScore,
    QueryRewriter,
    RagKnowledgePipeline,
    RagMatchPipeline,
    RetrievalScope,
    RewriteResult,
    SubQuestionIntents,
)
from verso_framework.config.app import AppSettings


class _FakeNormalizer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, uuid.UUID]] = []

    def normalize(self, text: str, *, user_id: uuid.UUID) -> str:
        self.calls.append((text, user_id))
        return text.replace("kodo", "对象存储")


class _FakeKnowledgePipeline:
    async def run(self, ctx: KnowledgeRetrieveContext) -> str:
        return ctx.query


class _FakeMatchPipeline:
    async def run(self, ctx: MatchRetrieveContext) -> str:
        return ctx.query


def test_knowledge_context_fields() -> None:
    user_id = uuid.uuid4()
    ctx = KnowledgeRetrieveContext(
        user_id=user_id,
        task_id=1,
        query="kodo如何配置",
        chat_history=[{"role": "user", "content": "上一轮"}],
    )
    result = RewriteResult(
        original_question=ctx.query,
        normalized_question="对象存储如何配置",
        rewritten_question="如何配置对象存储",
        sub_questions=["如何配置对象存储"],
        is_rewritten=True,
    )
    ctx.rewrite_result = result
    ctx.sub_question_intents = [
        SubQuestionIntents(
            sub_question="如何配置对象存储",
            node_scores=[NodeScore(node=IntentNode(name="对象存储"), score=0.9)],
        )
    ]

    assert ctx.user_id == user_id
    assert ctx.task_id == 1
    assert ctx.chat_history == [{"role": "user", "content": "上一轮"}]
    assert ctx.rewrite_result is result
    assert ctx.sub_question_intents[0].node_scores[0].score == 0.9
    assert not hasattr(ctx, "candidate_user_ids")


def test_match_context_requires_candidates_and_keeps_paired_scopes() -> None:
    asker_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    knowledge_base_id = uuid.uuid4()
    ctx = MatchRetrieveContext(
        user_id=asker_id,
        task_id=2,
        query="怎么配置对象存储",
        candidate_user_ids=[candidate_id],
    )
    ctx.retrieval_scopes = [
        RetrievalScope(user_id=candidate_id, knowledge_base_id=knowledge_base_id)
    ]

    assert ctx.user_id == asker_id
    assert ctx.candidate_user_ids == [candidate_id]
    assert ctx.retrieval_scopes[0].knowledge_base_id == knowledge_base_id
    with pytest.raises(ValidationError):
        MatchRetrieveContext(
            user_id=asker_id,
            task_id=2,
            query="怎么配置对象存储",
            candidate_user_ids=[],
        )


def test_pipeline_protocols_match_their_own_run_implementation() -> None:
    assert isinstance(_FakeKnowledgePipeline(), RagKnowledgePipeline)
    assert isinstance(_FakeMatchPipeline(), RagMatchPipeline)


class _FakeStructured:
    def __init__(self, payload: object, messages: list[object]) -> None:
        self._payload = payload
        self._messages = messages

    def invoke(self, messages: list[object]) -> object:
        self._messages.extend(messages)
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeModel:
    def __init__(self, payload: object) -> None:
        self.messages: list[object] = []
        self._payload = payload

    def with_structured_output(self, schema: object, **kwargs: object) -> _FakeStructured:
        del schema, kwargs
        return _FakeStructured(self._payload, self.messages)


def test_knowledge_rewrite_when_enabled_normalizes_before_model() -> None:
    normalizer = _FakeNormalizer()
    user_id = uuid.uuid4()
    model = _FakeModel(
        {
            "rewrite": "如何配置对象存储",
            "sub_questions": ["如何配置对象存储", "如何上传文档"],
        }
    )
    rewriter = QueryRewriter(
        normalizer,
        settings=AppSettings(query_rewrite_enabled=True),
        model=model,
    )
    ctx = KnowledgeRetrieveContext(
        user_id=user_id,
        task_id=1,
        query="kodo如何配置",
        chat_history=[{"role": "user", "content": "上一轮"}],
    )

    asyncio.run(rewriter.rewrite_knowledge(ctx))

    assert normalizer.calls == [("kodo如何配置", user_id)]
    assert ctx.rewrite_result is not None
    assert ctx.rewrite_result.original_question == "kodo如何配置"
    assert ctx.rewrite_result.normalized_question == "对象存储如何配置"
    assert ctx.rewrite_result.rewritten_question == "如何配置对象存储"
    assert ctx.rewrite_result.sub_questions == ["如何配置对象存储", "如何上传文档"]
    assert ctx.rewrite_result.is_rewritten is True
    system = next(message for message in model.messages if isinstance(message, SystemMessage))
    humans = [message for message in model.messages if isinstance(message, HumanMessage)]
    assert "你是查询改写助手" in system.content
    assert "上一轮" in humans[0].content
    assert "对象存储如何配置" in humans[-1].content


def test_knowledge_rewrite_falls_back_when_model_fails() -> None:
    rewriter = QueryRewriter(
        _FakeNormalizer(),
        settings=AppSettings(query_rewrite_enabled=True),
        model=_FakeModel(RuntimeError("timeout")),
    )
    ctx = KnowledgeRetrieveContext(
        user_id=uuid.uuid4(),
        task_id=1,
        query="kodo如何配置",
    )

    asyncio.run(rewriter.rewrite_knowledge(ctx))

    assert ctx.rewrite_result is not None
    assert ctx.rewrite_result.rewritten_question == "对象存储如何配置"
    assert ctx.rewrite_result.sub_questions == ["对象存储如何配置"]
    assert ctx.rewrite_result.is_rewritten is False


def test_query_rewrite_recovers_fenced_json() -> None:
    body = json.dumps(
        {"rewrite": "12306系统的架构", "sub_questions": ["12306系统的架构"]},
        ensure_ascii=False,
    )
    rewriter = QueryRewriter(
        _FakeNormalizer(),
        settings=AppSettings(query_rewrite_enabled=True),
        model=_FakeModel(
            {
                "parsed": None,
                "parsing_error": ValueError("fence"),
                "raw": AIMessage(content=f"```json\n{body}\n```"),
            }
        ),
    )
    ctx = KnowledgeRetrieveContext(
        user_id=uuid.uuid4(),
        task_id=1,
        query="请帮我详细介绍一下12306系统的架构",
    )

    asyncio.run(rewriter.rewrite_knowledge(ctx))

    assert ctx.rewrite_result is not None
    assert ctx.rewrite_result.rewritten_question == "12306系统的架构"
    assert ctx.rewrite_result.sub_questions == ["12306系统的架构"]
    assert ctx.rewrite_result.is_rewritten is True


def test_knowledge_rewrite_when_disabled_fills_normalized_question() -> None:
    user_id = uuid.uuid4()
    rewriter = QueryRewriter(_FakeNormalizer(), settings=AppSettings(query_rewrite_enabled=False))
    ctx = KnowledgeRetrieveContext(
        user_id=user_id,
        task_id=1,
        query="kodo如何配置",
        chat_history=[{"role": "user", "content": "上一轮"}],
    )

    asyncio.run(rewriter.rewrite_knowledge(ctx))

    assert ctx.rewrite_result is not None
    assert ctx.rewrite_result.original_question == "kodo如何配置"
    assert ctx.rewrite_result.normalized_question == "对象存储如何配置"
    assert ctx.rewrite_result.rewritten_question == "对象存储如何配置"
    assert ctx.rewrite_result.sub_questions == ["对象存储如何配置"]
    assert ctx.rewrite_result.is_rewritten is False


def test_match_rewrite_skips_normalization() -> None:
    normalizer = _FakeNormalizer()
    model = _FakeModel(
        {
            "rewrite": "如何配置对象存储",
            "sub_questions": ["如何配置对象存储"],
        }
    )
    rewriter = QueryRewriter(
        normalizer,
        settings=AppSettings(query_rewrite_enabled=True),
        model=model,
    )
    ctx = MatchRetrieveContext(
        user_id=uuid.uuid4(),
        task_id=2,
        query="kodo如何配置",
        candidate_user_ids=[uuid.uuid4()],
        chat_history=[{"role": "user", "content": "上一轮"}],
    )

    asyncio.run(rewriter.rewrite_match(ctx))

    assert normalizer.calls == []
    assert ctx.rewrite_result is not None
    assert ctx.rewrite_result.normalized_question == "kodo如何配置"
    assert ctx.rewrite_result.rewritten_question == "如何配置对象存储"
    assert ctx.rewrite_result.is_rewritten is True
    humans = [message for message in model.messages if isinstance(message, HumanMessage)]
    assert "kodo如何配置" in humans[-1].content


def test_match_rewrite_when_disabled_keeps_original_question() -> None:
    normalizer = _FakeNormalizer()
    rewriter = QueryRewriter(normalizer, settings=AppSettings(query_rewrite_enabled=False))
    ctx = MatchRetrieveContext(
        user_id=uuid.uuid4(),
        task_id=2,
        query="kodo如何配置",
        candidate_user_ids=[uuid.uuid4()],
    )

    asyncio.run(rewriter.rewrite_match(ctx))

    assert normalizer.calls == []
    assert ctx.rewrite_result is not None
    assert ctx.rewrite_result.normalized_question == "kodo如何配置"
    assert ctx.rewrite_result.is_rewritten is False
