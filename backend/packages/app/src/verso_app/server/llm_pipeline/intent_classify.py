"""意图分类的大模型调用。

系统提示词在 ``templates/intent_classifier.jinja2``。路径由
``INTENT_CLASSIFIER_PROMPT_PATH`` 指向，默认相对本包目录。
调用方传入该用户当前的意图节点；本模块只对启用的知识库叶子打分。
模型返回 JSON 数组 ``[{"id", "score", "reason"}]``。解析失败时返回空列表。
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from verso_app.server.intent.models import IntentNode
from verso_app.server.retrieve.models import NodeScore
from verso_common.enums import IntentKind
from verso_framework.config.app import AppSettings
from verso_framework.providers.llm import build_chat_model

logger = logging.getLogger("verso.llm_pipeline.intent_classify")

_TEMPERATURE = 0.1
_TOP_P = 0.3


def classify_targets(
    question: str,
    nodes: list[IntentNode],
    *,
    settings: AppSettings,
    model: BaseChatModel | None = None,
) -> list[NodeScore]:
    """对一条问题做意图打分，按 score 从高到低返回。失败时返回空列表。"""
    leaves = _candidate_leaves(nodes)
    if not leaves:
        logger.debug("意图树没有可用叶子节点，跳过 LLM 意图识别")
        return []

    messages: list[BaseMessage] = [
        SystemMessage(content=_render_prompt(leaves, nodes, settings)),
        HumanMessage(content=question),
    ]
    chat = _prepare_model(model, settings)
    try:
        raw = chat.invoke(messages)
    except Exception:
        logger.warning("意图识别 LLM 调用失败，返回空意图", exc_info=True)
        return []
    return _parse_scores(_message_text(raw), leaves, question)


def _candidate_leaves(nodes: list[IntentNode]) -> list[IntentNode]:
    """启用的知识库叶子。父节点和停用节点不进入分类列表。"""
    enabled = [node for node in nodes if node.enabled]
    parent_ids = {node.parent_id for node in enabled if node.parent_id is not None}
    leaves: list[IntentNode] = []
    seen: set[str] = set()
    for node in enabled:
        if node.id in parent_ids or node.kind != IntentKind.KB_RETRIEVE:
            continue
        if not node.identifier or node.identifier in seen:
            if node.identifier in seen:
                logger.warning("意图节点 identifier 重复，已跳过: %s", node.identifier)
            continue
        seen.add(node.identifier)
        leaves.append(node)
    return leaves


def _render_prompt(
    leaves: list[IntentNode],
    nodes: list[IntentNode],
    settings: AppSettings,
) -> str:
    by_id = {node.id: node for node in nodes}
    template = _load_prompt(settings.intent_classifier_prompt_path)
    intent_list = _format_intent_list(leaves, by_id)
    if "{intent_list}" not in template:
        logger.warning("意图分类模板缺少 {intent_list} 占位符")
        return template
    return template.replace("{intent_list}", intent_list)


def _format_intent_list(leaves: list[IntentNode], by_id: dict[uuid.UUID, IntentNode]) -> str:
    blocks: list[str] = []
    for node in leaves:
        lines = [
            f"- id={node.identifier}",
            f"  path={_full_path(node, by_id)}",
            f"  description={node.description}",
            "  type=SYSTEM" if node.kind != IntentKind.KB_RETRIEVE else "  type=KB",
        ]
        examples = _format_examples(node.examples)
        if examples:
            lines.append(f"  examples={examples}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _full_path(node: IntentNode, by_id: dict[uuid.UUID, IntentNode]) -> str:
    names = [node.name]
    seen = {node.id}
    current = node
    while current.parent_id is not None and current.parent_id not in seen:
        parent = by_id.get(current.parent_id)
        if parent is None:
            break
        seen.add(parent.id)
        names.append(parent.name)
        current = parent
    return " > ".join(reversed(names))


def _format_examples(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("意图节点 examples 不是合法 JSON 数组")
            parsed = None
        if isinstance(parsed, list):
            items = [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
            return " / ".join(items) if items else None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return " / ".join(lines)
    return text


def _prepare_model(model: BaseChatModel | None, settings: AppSettings) -> BaseChatModel:
    chat = model if model is not None else build_chat_model(settings)
    bind = getattr(chat, "bind", None)
    if bind is None:
        return chat
    return bind(temperature=_TEMPERATURE, top_p=_TOP_P)


def _parse_scores(raw: str, leaves: list[IntentNode], question: str) -> list[NodeScore]:
    by_identifier = {node.identifier: node for node in leaves}
    try:
        payload = json.loads(_strip_code_fences(raw))
    except json.JSONDecodeError:
        logger.warning("意图打分解析失败，返回空意图")
        return []

    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        items = payload["results"]
    elif isinstance(payload, list):
        items = payload
    else:
        logger.warning("LLM 返回了非预期的 JSON 格式")
        return []

    scores: list[NodeScore] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        score = item.get("score")
        if (
            not isinstance(identifier, str)
            or isinstance(score, bool)
            or not isinstance(score, int | float)
        ):
            continue
        node = by_identifier.get(identifier)
        if node is None:
            logger.warning("LLM 返回了未知或当前不可用的意图节点 ID: %s，已跳过", identifier)
            continue
        scores.append(NodeScore(node=node, score=float(score)))

    scores.sort(key=lambda item: item.score, reverse=True)
    logger.info(
        "意图识别：问题=%s 命中=%s",
        question,
        [(item.node.identifier, item.score) for item in scores],
    )
    return scores


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        body = stripped[first_newline + 1 :] if first_newline != -1 else stripped[3:]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
        return body.strip()
    return stripped


def _message_text(raw: object) -> str:
    content = getattr(raw, "content", raw)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    if isinstance(content, str):
        return content
    return str(content)


def _load_prompt(path: str) -> str:
    candidate = Path(path)
    if not candidate.is_file():
        candidate = Path(__file__).resolve().parent / path
    return candidate.read_text(encoding="utf-8")
