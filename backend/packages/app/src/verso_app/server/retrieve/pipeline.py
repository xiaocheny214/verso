"""RAG 检索管道契约。

专属知识库与匹配检索各持有一份上下文。环节读已有字段，把结果写回同一对象。
``run`` 的返回值留给后续检索结果模型。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from verso_app.server.retrieve.models import KnowledgeRetrieveContext, MatchRetrieveContext


@runtime_checkable
class RagKnowledgePipeline(Protocol):
    """专属知识库管道。"""

    async def run(self, ctx: KnowledgeRetrieveContext) -> Any: ...


@runtime_checkable
class RagMatchPipeline(Protocol):
    """匹配检索管道。只在候选用户内检索，不扫全库。"""

    async def run(self, ctx: MatchRetrieveContext) -> Any: ...
