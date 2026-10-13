"""RAG Pipeline 上下文接口与 QueryRewriter 单元测试。"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from verso_app.server.auth.models import User
from verso_app.server.retrieve.pipeline import (
    RagGlobalPipeline,
    RagKnowledgePipeline,
    RetrieveContext,
)
from verso_app.server.retrieve.rewrite import (
    QueryRewriter,
    RewriteConfig,
    build_query_rewriter,
)
from verso_app.server.retrieve.term_mapping.service import QueryTermMappingService
from verso_framework.config.app import AppSettings
from verso_framework.db.base import Base


class _Message:
    def __init__(self, content: str | dict | list) -> None:
        self.content = content


class _Structured:
    def __init__(self, response: object) -> None:
        self.response = response
        self.messages = None

    def invoke(self, messages: list):
        self.messages = messages
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, str):
            return _Message(self.response)
        return self.response


class _Model:
    def __init__(self, response: object) -> None:
        self.response = response
        self.structured = None

    def with_structured_output(self, schema, **kwargs):
        self.structured = _Structured(self.response)
        return self.structured


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def user(db: Session) -> User:
    u = User(
        display_name="测试用户",
        zhihu_url_token="tok_123",
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def term_service(db: Session) -> QueryTermMappingService:
    return QueryTermMappingService(session=db, redis=None)


def test_protocol_conformance() -> None:
    """验证 RagKnowledgePipeline 与 RagGlobalPipeline 的 Protocol 一致性。"""

    class DummyKnowledgePipeline:
        def run(self, ctx: RetrieveContext) -> dict:
            return {"status": "ok"}

    class DummyGlobalPipeline:
        def run(self, ctx: RetrieveContext) -> list:
            return []

    assert isinstance(DummyKnowledgePipeline(), RagKnowledgePipeline)
    assert isinstance(DummyGlobalPipeline(), RagGlobalPipeline)


def test_rewrite_normalizes_before_llm(user: User, term_service: QueryTermMappingService) -> None:
    """验证在提问包含映射词时，先执行术语归一化，且 LLM 接收到归一化提问。"""
    term_service.create(
        user_id=user.id,
        source_term="kodo",
        target_term="对象存储",
    )

    llm_output = {
        "rewritten_question": "七牛云对象存储配置方法是什么？",
        "sub_questions": ["七牛云对象存储配置方法是什么？"],
    }
    mock_model = _Model({"parsed": llm_output, "raw": _Message(json.dumps(llm_output))})
    rewriter = QueryRewriter(term_mapping=term_service, model=mock_model)

    ctx = RetrieveContext(
        user_id=user.id,
        query="请问kodo的存储策略是什么？",
    )
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is True
    assert res.original_question == "请问kodo的存储策略是什么？"
    assert res.normalized_question == "请问对象存储的存储策略是什么？"
    assert res.rewritten_question == "七牛云对象存储配置方法是什么？"
    assert res.sub_questions == ["七牛云对象存储配置方法是什么？"]

    # 验证 HumanMessage 传入了归一化词
    assert mock_model.structured is not None
    human_msg = mock_model.structured.messages[1]
    assert "请问对象存储的存储策略是什么？" in human_msg.content
    assert "请问kodo的存储策略是什么？" in human_msg.content


def test_rewrite_disabled_skips_llm(user: User, term_service: QueryTermMappingService) -> None:
    """验证当 RewriteConfig.enabled=False 时跳过 LLM，直接返回归一化结果。"""
    term_service.create(
        user_id=user.id,
        source_term="kodo",
        target_term="对象存储",
    )
    mock_model = _Model(Exception("Should not be called"))
    rewriter = QueryRewriter(
        term_mapping=term_service,
        model=mock_model,
        config=RewriteConfig(enabled=False),
    )

    ctx = RetrieveContext(user_id=user.id, query="kodo使用指南")
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is False
    assert res.original_question == "kodo使用指南"
    assert res.normalized_question == "对象存储使用指南"
    assert res.rewritten_question == "对象存储使用指南"
    assert res.sub_questions == ["对象存储使用指南"]
    assert mock_model.structured is None


def test_rewrite_no_model_skips_llm(user: User, term_service: QueryTermMappingService) -> None:
    """验证当 model=None 时直接降级，返回归一化结果。"""
    rewriter = QueryRewriter(term_mapping=term_service, model=None)

    ctx = RetrieveContext(user_id=user.id, query="测试提问")
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is False
    assert res.rewritten_question == "测试提问"
    assert res.sub_questions == ["测试提问"]


def test_rewrite_success_parses_sub_questions(
    user: User, term_service: QueryTermMappingService
) -> None:
    """验证正常调用返回独立主问题与子问题列表。"""
    llm_output = {
        "rewritten_question": "如何创建知识库以及如何向知识库上传文档？",
        "sub_questions": [
            "如何创建知识库？",
            "如何向知识库上传文档？",
        ],
    }
    mock_model = _Model(json.dumps(llm_output))
    rewriter = QueryRewriter(term_mapping=term_service, model=mock_model)

    ctx = RetrieveContext(user_id=user.id, query="怎么创建知识库并且上传文档")
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is True
    assert res.rewritten_question == "如何创建知识库以及如何向知识库上传文档？"
    assert res.sub_questions == ["如何创建知识库？", "如何向知识库上传文档？"]


def test_rewrite_llm_exception_degrades_gracefully(
    user: User, term_service: QueryTermMappingService
) -> None:
    """验证 LLM 抛出异常（网络超时等）时优雅降级。"""
    term_service.create(
        user_id=user.id,
        source_term="向量",
        target_term="Embedding特征",
    )
    mock_model = _Model(TimeoutError("LLM Gateway timeout"))
    rewriter = QueryRewriter(term_mapping=term_service, model=mock_model)

    ctx = RetrieveContext(user_id=user.id, query="向量检索原理")
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is False
    assert res.original_question == "向量检索原理"
    assert res.normalized_question == "Embedding特征检索原理"
    assert res.rewritten_question == "Embedding特征检索原理"
    assert res.sub_questions == ["Embedding特征检索原理"]


def test_rewrite_invalid_json_degrades_gracefully(
    user: User, term_service: QueryTermMappingService
) -> None:
    """验证 LLM 返回非法非 JSON 文本时优雅降级。"""
    mock_model = _Model(_Message("抱歉，我无法回答这个问题。"))
    rewriter = QueryRewriter(term_mapping=term_service, model=mock_model)

    ctx = RetrieveContext(user_id=user.id, query="系统架构设计")
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is False
    assert res.rewritten_question == "系统架构设计"
    assert res.sub_questions == ["系统架构设计"]


def test_rewrite_with_chat_history(user: User, term_service: QueryTermMappingService) -> None:
    """验证传入 chat_history 时正确拼入 Prompt 消息中。"""
    llm_output = {
        "rewritten_question": "PostgreSQL 向量插件 pgvector 的安装步骤是什么？",
        "sub_questions": ["PostgreSQL 向量插件 pgvector 的安装步骤是什么？"],
    }
    mock_model = _Model(json.dumps(llm_output))
    rewriter = QueryRewriter(term_mapping=term_service, model=mock_model)

    ctx = RetrieveContext(
        user_id=user.id,
        query="它怎么安装？",
        chat_history=[
            {"role": "user", "content": "我想了解一下 pgvector"},
            {"role": "assistant", "content": "pgvector 是 PostgreSQL 的向量扩展。"},
        ],
    )
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is True
    assert mock_model.structured is not None
    human_msg = mock_model.structured.messages[1]
    assert "历史对话上下文：" in human_msg.content
    assert "用户: 我想了解一下 pgvector" in human_msg.content
    assert "助手: pgvector 是 PostgreSQL 的向量扩展。" in human_msg.content


def test_rewrite_strips_code_fences(user: User, term_service: QueryTermMappingService) -> None:
    """验证带有 markdown ```json 代码块的返回能正确解析。"""
    fenced_output = """```json
{
  "rewritten_question": "FastAPI 依赖注入原理",
  "sub_questions": ["FastAPI 依赖注入原理"]
}
```"""
    mock_model = _Model(_Message(fenced_output))
    rewriter = QueryRewriter(term_mapping=term_service, model=mock_model)

    ctx = RetrieveContext(user_id=user.id, query="FastAPI DI原理")
    res = rewriter.rewrite(ctx)

    assert res.is_rewritten is True
    assert res.rewritten_question == "FastAPI 依赖注入原理"
    assert res.sub_questions == ["FastAPI 依赖注入原理"]


def test_build_query_rewriter(term_service: QueryTermMappingService) -> None:
    """验证 build_query_rewriter 工厂方法。"""
    # 无 API key 时 model 为 None
    settings_no_key = AppSettings(llm_api_key="", llm_model="")
    rewriter_no_key = build_query_rewriter(settings_no_key, term_service)
    assert rewriter_no_key._model is None

    # 配置了 API key 时正常构建模型
    settings_with_key = AppSettings(llm_api_key="test-key", llm_model="gpt-4o-mini")
    rewriter_with_key = build_query_rewriter(settings_with_key, term_service)
    assert rewriter_with_key._model is not None
