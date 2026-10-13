"""大模型查询改写与子问题拆分核心组件。"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, TypeGuard

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from verso_app.server.retrieve.pipeline import RetrieveContext
from verso_framework.providers.llm import build_chat_model

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from verso_app.server.retrieve.term_mapping.service import QueryTermMappingService
    from verso_framework.config.app import AppSettings

logger = logging.getLogger("verso.retrieve.rewrite")

_SYSTEM_PROMPT = """你是 Verso 的查询改写助手。你的任务是：
1. 将用户输入改写为一条语义清晰、适合向量检索的完整检索主问题。
2. 将复合意图拆分为独立互补的子问题列表。

规则：
- 如果问题已经足够清晰且只有单一意图，rewritten_question 与输入保持一致，sub_questions 只含该问题。
- 子问题之间不能有语义重叠，每条子问题应当能独立进行检索。
- 不要回答用户的问题，只做改写和拆分。

只输出 JSON，形状必须是：
{"rewritten_question":"...","sub_questions":["...","..."]}
"""

_USER_PROMPT = """用户原始提问：
{original_question}

归一化后的提问：
{normalized_question}

{history_block}请基于以上信息完成查询改写与子问题拆分。"""

_REWRITE_JSON_SCHEMA: dict[str, object] = {
    "title": "LlmRewriteOutput",
    "type": "object",
    "properties": {
        "rewritten_question": {"type": "string"},
        "sub_questions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["rewritten_question", "sub_questions"],
}


class RewriteConfig(BaseModel):
    """查询改写配置。"""

    enabled: bool = True


class RewriteResult(BaseModel):
    """查询改写输出结果。"""

    original_question: str
    normalized_question: str
    rewritten_question: str
    sub_questions: list[str]
    is_rewritten: bool


class _LlmRewriteOutput(BaseModel):
    rewritten_question: str = Field(min_length=1)
    sub_questions: list[str] = Field(default_factory=list)


def _strip_code_fences(text: str) -> str:
    """去除 markdown 代码块标记。"""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        body = stripped[first_newline + 1 :] if first_newline != -1 else stripped[3:]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
        return body.strip()
    return stripped


def _message_payload(raw: object) -> object:
    """提取 LangChain message content。"""
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


def _is_include_raw_payload(raw: object) -> TypeGuard[dict]:
    return (
        isinstance(raw, dict)
        and "raw" in raw
        and ("parsed" in raw or "parsing_error" in raw)
        and "rewritten_question" not in raw
    )


def _parse_llm_output(raw: object) -> _LlmRewriteOutput:
    """将 LLM 输出解析为 _LlmRewriteOutput。"""
    if isinstance(raw, _LlmRewriteOutput):
        return raw
    payload = _message_payload(raw)
    if isinstance(payload, str):
        payload = json.loads(_strip_code_fences(payload))
    if isinstance(payload, dict):
        return _LlmRewriteOutput.model_validate(payload)
    raise ValueError(f"无法识别的 LLM 输出格式: {type(raw)}")


def _parse_structured_output(raw: object) -> _LlmRewriteOutput:
    """解析带有 include_raw=True 的结构化响应。"""
    if not _is_include_raw_payload(raw):
        return _parse_llm_output(raw)
    parsed = raw.get("parsed")
    if parsed is not None:
        return _parse_llm_output(parsed)
    return _parse_llm_output(raw.get("raw"))


def _format_chat_history(chat_history: list[dict[str, str]]) -> str:
    """将历史对话格式化为 Prompt 文本段。"""
    if not chat_history:
        return ""
    lines: list[str] = ["历史对话上下文："]
    for msg in chat_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "").strip()
        if not content:
            continue
        role_label = "用户" if role == "user" else "助手" if role == "assistant" else role
        lines.append(f"{role_label}: {content}")
    lines.append("")
    return "\n".join(lines) + "\n"


class QueryRewriter:
    """大模型查询改写核心服务。"""

    def __init__(
        self,
        *,
        term_mapping: QueryTermMappingService,
        model: BaseChatModel | None = None,
        config: RewriteConfig | None = None,
    ) -> None:
        self._term_mapping = term_mapping
        self._model = model
        self._config = config or RewriteConfig()
        self._structured = (
            model.with_structured_output(
                _REWRITE_JSON_SCHEMA,
                method="json_mode",
                include_raw=True,
            )
            if model is not None and self._config.enabled
            else None
        )

    def rewrite(self, ctx: RetrieveContext) -> RewriteResult:
        """执行术语归一化、复杂长句改写与子问题拆分。"""
        # 1. 术语归一化
        normalized = self._term_mapping.normalize(ctx.query, user_id=ctx.user_id)

        # 2. 降级防线 1：未启用改写或模型未配置
        if not self._config.enabled or self._structured is None:
            return RewriteResult(
                original_question=ctx.query,
                normalized_question=normalized,
                rewritten_question=normalized,
                sub_questions=[normalized],
                is_rewritten=False,
            )

        # 3. 构造 Prompt 上下文
        history_block = _format_chat_history(ctx.chat_history)
        user_message_content = _USER_PROMPT.format(
            original_question=ctx.query,
            normalized_question=normalized,
            history_block=history_block,
        )

        # 4. 驱动 LLM 结构化输出与降级防线 2
        try:
            raw = self._structured.invoke(
                [
                    SystemMessage(content=_SYSTEM_PROMPT),
                    HumanMessage(content=user_message_content),
                ]
            )
            parsed = _parse_structured_output(raw)
            rewritten_q = parsed.rewritten_question.strip()
            sub_qs = [q.strip() for q in parsed.sub_questions if q.strip()]
            if not sub_qs:
                sub_qs = [rewritten_q]

            return RewriteResult(
                original_question=ctx.query,
                normalized_question=normalized,
                rewritten_question=rewritten_q,
                sub_questions=sub_qs,
                is_rewritten=True,
            )
        except Exception as exc:
            logger.warning("查询改写大模型调用或解析异常，优雅降级: %s", exc, exc_info=True)
            return RewriteResult(
                original_question=ctx.query,
                normalized_question=normalized,
                rewritten_question=normalized,
                sub_questions=[normalized],
                is_rewritten=False,
            )


def build_query_rewriter(
    settings: AppSettings,
    term_mapping: QueryTermMappingService,
) -> QueryRewriter:
    """根据系统配置构建 QueryRewriter 实例。"""
    model = None
    if settings.llm_api_key and settings.llm_model:
        model = build_chat_model(settings)
    return QueryRewriter(term_mapping=term_mapping, model=model)
