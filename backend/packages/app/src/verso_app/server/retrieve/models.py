"""检索管道的内存模型。

这些对象沿管道传递并被逐步填满，不对应数据库表。
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from verso_app.server.intent.models import IntentNode


class RewriteResult(BaseModel):
    """查询改写写入上下文的结果。"""

    original_question: str
    normalized_question: str
    rewritten_question: str
    sub_questions: list[str] = Field(default_factory=list)
    is_rewritten: bool


class NodeScore(BaseModel):
    """一个意图节点对某条子问题的匹配分。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    node: IntentNode
    score: float


class SubQuestionIntents(BaseModel):
    """一条子问题，以及它命中的意图节点分数。"""

    sub_question: str
    node_scores: list[NodeScore] = Field(default_factory=list)


class RetrievalScope(BaseModel):
    """一条向量检索过滤条件：某个用户的某个知识库。"""

    user_id: uuid.UUID
    knowledge_base_id: uuid.UUID


class KnowledgeRetrieveContext(BaseModel):
    """专属知识库管道的上下文。意图树只取 ``user_id`` 名下的节点。

    调用方传入 ``user_id``、``task_id``、``query``、``chat_history``。
    后续环节把 ``rewrite_result``、``sub_question_intents`` 填回同一对象。
    """

    user_id: uuid.UUID
    task_id: int
    query: str
    chat_history: list[dict[str, str]] = Field(default_factory=list)
    rewrite_result: RewriteResult | None = None
    sub_question_intents: list[SubQuestionIntents] = Field(default_factory=list)


class MatchRetrieveContext(BaseModel):
    """匹配检索管道的上下文。

    ``user_id`` 是提问者，不参与意图树加载。
    ``candidate_user_ids`` 是候选池，调用时必须非空。
    ``retrieval_scopes`` 由后续环节按命中节点收成成对过滤条件。
    """

    user_id: uuid.UUID
    task_id: int
    query: str
    chat_history: list[dict[str, str]] = Field(default_factory=list)
    candidate_user_ids: list[uuid.UUID] = Field(min_length=1)
    rewrite_result: RewriteResult | None = None
    sub_question_intents: list[SubQuestionIntents] = Field(default_factory=list)
    retrieval_scopes: list[RetrievalScope] = Field(default_factory=list)
