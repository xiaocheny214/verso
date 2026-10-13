"""RAG Pipeline 统一上下文与 Protocol 接口定义。"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class RetrieveContext(BaseModel):
    """检索流水线执行上下文。"""

    user_id: uuid.UUID
    knowledge_base_id: uuid.UUID | None = None
    query: str
    chat_history: list[dict[str, str]] = Field(default_factory=list)
    extra_params: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class RagKnowledgePipeline(Protocol):
    """专属知识库 RAG 流水线接口。"""

    def run(self, ctx: RetrieveContext) -> Any: ...


@runtime_checkable
class RagGlobalPipeline(Protocol):
    """全站跨库 RAG 流水线接口。"""

    def run(self, ctx: RetrieveContext) -> Any: ...
