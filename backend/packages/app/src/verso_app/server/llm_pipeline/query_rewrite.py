"""查询改写的大模型调用。

系统提示词在 ``templates/query_rewrite.jinja2``。路径由
``QUERY_REWRITE_AND_SPLIT_PROMPT_PATH`` 指向，默认相对本包目录。
模型用 ``json_mode`` 返回 ``rewrite`` 与 ``sub_questions``。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeGuard

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from verso_app.server.retrieve.models import RewriteResult
from verso_common.constants import QUERY_REWRITE_ASSISTANT_HISTORY_LIMIT
from verso_framework.config.app import AppSettings
from verso_framework.providers.llm import build_chat_model

logger = logging.getLogger("verso.llm_pipeline.query_rewrite")

_LLM_QUERY_REWRITE_JSON_SCHEMA: dict[str, object] = {
    "title": "LlmQueryRewrite",
    "type": "object",
    "properties": {
        "rewrite": {"type": "string", "minLength": 1},
        "sub_questions": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string"},
        },
    },
    "required": ["rewrite", "sub_questions"],
}


class LlmQueryRewrite(BaseModel):
    """模板要求的模型输出。``rewrite`` 对应上下文里的 ``rewritten_question``。"""

    rewrite: str = Field(min_length=1)
    sub_questions: list[str] = Field(min_length=1)


def rewrite_query(
    *,
    original_question: str,
    question: str,
    chat_history: list[dict[str, str]],
    settings: AppSettings,
    model: BaseChatModel | None = None,
) -> RewriteResult:
    """改写当前问题。失败时用 ``question`` 兜底。"""
    fallback = RewriteResult(
        original_question=original_question,
        normalized_question=question,
        rewritten_question=question,
        sub_questions=[question],
        is_rewritten=False,
    )
    try:
        parsed = _call_model(
            original_question,
            question,
            chat_history,
            settings,
            model,
        )
        result = parsed if parsed is not None else fallback
    except Exception:
        logger.warning("查询改写 LLM 调用失败，使用当前问题兜底", exc_info=True)
        result = fallback
    logger.info(
        "RAG用户问题查询改写+拆分：原始问题=%s 送入模型=%s 改写结果=%s 子问题=%s",
        original_question,
        question,
        result.rewritten_question,
        result.sub_questions,
    )
    return result


def _call_model(
    original_question: str,
    question: str,
    chat_history: list[dict[str, str]],
    settings: AppSettings,
    model: BaseChatModel | None,
) -> RewriteResult | None:
    system_prompt = _load_prompt(settings.query_rewrite_prompt_path)
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        *_select_rewrite_history(chat_history),
        HumanMessage(content=question),
    ]
    chat = model if model is not None else build_chat_model(settings)
    structured = chat.with_structured_output(
        _LLM_QUERY_REWRITE_JSON_SCHEMA,
        method="json_mode",
        include_raw=True,
    )
    raw = structured.invoke(messages)
    parsed = _parse_structured_rewrite(raw)
    sub_questions = [item.strip() for item in parsed.sub_questions if item.strip()]
    rewritten = parsed.rewrite.strip()
    if not rewritten or not sub_questions:
        return None
    return RewriteResult(
        original_question=original_question,
        normalized_question=question,
        rewritten_question=rewritten,
        sub_questions=sub_questions,
        is_rewritten=True,
    )


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        body = stripped[first_newline + 1 :] if first_newline != -1 else stripped[3:]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
        return body.strip()
    return stripped


def _message_payload(raw: object) -> object:
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


def _parse_llm_rewrite(raw: object) -> LlmQueryRewrite:
    if isinstance(raw, LlmQueryRewrite):
        return raw
    payload = _message_payload(raw)
    if isinstance(payload, str):
        payload = json.loads(_strip_code_fences(payload))
    return LlmQueryRewrite.model_validate(payload)


def _is_include_raw_payload(raw: object) -> TypeGuard[dict]:
    return (
        isinstance(raw, dict)
        and "raw" in raw
        and ("parsed" in raw or "parsing_error" in raw)
        and "rewrite" not in raw
    )


def _parse_structured_rewrite(raw: object) -> LlmQueryRewrite:
    """优先用 json_mode 已解析的对象，否则从原始消息里取出 JSON。"""
    if not _is_include_raw_payload(raw):
        return _parse_llm_rewrite(raw)
    parsed = raw.get("parsed")
    if parsed is not None:
        return _parse_llm_rewrite(parsed)
    return _parse_llm_rewrite(raw.get("raw"))


def _load_prompt(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_file():
        candidate = Path(__file__).resolve().parent / path
    return candidate.read_text(encoding="utf-8")


def _select_rewrite_history(chat_history: list[dict[str, str]]) -> list[BaseMessage]:
    """历史用户提问全部保留，助手回答只保留最近若干条。"""
    assistant_indexes = [
        index
        for index, item in enumerate(chat_history)
        if item.get("role") == "assistant" and item.get("content", "").strip()
    ]
    kept_assistants = set(assistant_indexes[-QUERY_REWRITE_ASSISTANT_HISTORY_LIMIT:])
    selected: list[BaseMessage] = []
    for index, item in enumerate(chat_history):
        content = item.get("content", "").strip()
        role = item.get("role", "")
        if not content:
            continue
        if role == "user":
            selected.append(HumanMessage(content=content))
        elif role == "assistant" and index in kept_assistants:
            selected.append(AIMessage(content=content))
    return selected
