"""查询改写。

知识库改写先按当前用户做术语归一化，再进入大模型。匹配改写不做归一化。
大模型调用在 ``llm_pipeline.query_rewrite``。
是否调用大模型由 ``VERSO_QUERY_REWRITE_ENABLED`` 决定，默认开启。
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from langchain_core.language_models import BaseChatModel

from verso_app.server.llm_pipeline.query_rewrite import rewrite_query
from verso_app.server.retrieve.models import (
    KnowledgeRetrieveContext,
    MatchRetrieveContext,
    RewriteResult,
)
from verso_framework.config.app import AppSettings, get_app_settings


@runtime_checkable
class QueryTermNormalizer(Protocol):
    """术语归一化。只给知识库改写使用，实现是 ``term_mapping.QueryTermMappingService``。"""

    def normalize(self, text: str, *, user_id: uuid.UUID) -> str: ...


class QueryRewriter:
    """把改写结果填回当前管道的上下文。"""

    def __init__(
        self,
        term_normalizer: QueryTermNormalizer,
        *,
        settings: AppSettings | None = None,
        model: BaseChatModel | None = None,
    ) -> None:
        self._term_normalizer = term_normalizer
        self._settings = settings if settings is not None else get_app_settings()
        self._model = model

    async def rewrite_knowledge(self, ctx: KnowledgeRetrieveContext) -> None:
        normalized = self._term_normalizer.normalize(ctx.query, user_id=ctx.user_id)
        if not self._settings.query_rewrite_enabled:
            ctx.rewrite_result = _fallback(ctx.query, normalized)
            return
        ctx.rewrite_result = rewrite_query(
            original_question=ctx.query,
            question=normalized,
            chat_history=ctx.chat_history,
            settings=self._settings,
            model=self._model,
        )

    async def rewrite_match(self, ctx: MatchRetrieveContext) -> None:
        if not self._settings.query_rewrite_enabled:
            ctx.rewrite_result = _fallback(ctx.query, ctx.query)
            return
        ctx.rewrite_result = rewrite_query(
            original_question=ctx.query,
            question=ctx.query,
            chat_history=ctx.chat_history,
            settings=self._settings,
            model=self._model,
        )


def _fallback(original_question: str, question: str) -> RewriteResult:
    return RewriteResult(
        original_question=original_question,
        normalized_question=question,
        rewritten_question=question,
        sub_questions=[question],
        is_rewritten=False,
    )
