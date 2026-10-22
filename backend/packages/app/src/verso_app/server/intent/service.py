"""用户意图节点 CRUD 与树结构校验。

节点存储为扁平父子关系，写入一次一个节点，读取可输出已装配好的森林结构。
一个用户可以有多棵根树。Redis 按用户缓存整片森林，键里带 user_id，租户之间不共用。
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from verso_app.server.intent.models import IntentNode
from verso_app.server.knowledge.models import KnowledgeBase
from verso_common.enums import BizCode, IntentKind, IntentLayer
from verso_common.exceptions import BizException

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger("verso.intent")

CACHE_KEY_PREFIX = "verso:intent_trees:"
CACHE_TTL_SECONDS = 3600
EMPTY_CACHE_SENTINEL = "__empty__"
_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_UNSET = object()


class IntentService:
    """当前用户拥有的意图节点服务。"""

    def __init__(self, redis: Redis | None = None) -> None:
        self._redis = redis

    def _cache_key(self, user_id: uuid.UUID) -> str:
        return f"{CACHE_KEY_PREFIX}{user_id}"

    def _invalidate_cache(self, user_id: uuid.UUID) -> None:
        if self._redis is None:
            return
        try:
            self._redis.delete(self._cache_key(user_id))
        except Exception as exc:
            logger.warning("删除 Redis 意图树缓存失败 user_id=%s: %s", user_id, exc)

    def _validate_identifier(self, identifier: str) -> str:
        clean = identifier.strip()
        if not clean:
            raise BizException("节点唯一标识 identifier 不能为空", code=BizCode.BAD_REQUEST)
        if not _IDENTIFIER_RE.match(clean):
            raise BizException(
                "identifier 只能包含字母、数字和下划线",
                code=BizCode.BAD_REQUEST,
            )
        return clean

    def _validate_name(self, name: str) -> str:
        clean = name.strip()
        if not clean:
            raise BizException("意图节点名称不能为空", code=BizCode.BAD_REQUEST)
        return clean

    def _validate_kind(self, kind: str) -> str:
        clean = kind.strip()
        if clean != IntentKind.KB_RETRIEVE:
            raise BizException(
                f"当前仅支持 kind='{IntentKind.KB_RETRIEVE}'",
                code=BizCode.BAD_REQUEST,
            )
        return clean

    def _validate_layer(self, layer: str) -> str:
        clean = layer.strip()
        valid_layers = {IntentLayer.DOMAIN, IntentLayer.TOPIC, IntentLayer.OTHER}
        if clean not in valid_layers:
            raise BizException(
                f"layer 必须为 {', '.join(valid_layers)} 之一",
                code=BizCode.BAD_REQUEST,
            )
        return clean

    def _check_identifier_unique(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        identifier: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        query = select(IntentNode.id).where(
            IntentNode.user_id == user_id,
            IntentNode.identifier == identifier,
        )
        if exclude_id is not None:
            query = query.where(IntentNode.id != exclude_id)
        if db.scalar(query) is not None:
            raise BizException("该唯一标识 identifier 已被占用", code=BizCode.CONFLICT)

    def _check_knowledge_base_owned(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID | None,
    ) -> None:
        if knowledge_base_id is None:
            return
        row = db.scalar(
            select(KnowledgeBase.id).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        if row is None:
            raise BizException("知识库不存在", code=BizCode.NOT_FOUND)

    def _check_cycle(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        new_parent_id: uuid.UUID,
    ) -> None:
        """从 new_parent_id 沿树向上追溯，若遇到 node_id 则拒绝成环。"""
        if new_parent_id == node_id:
            raise BizException("不能将节点设为自身的子节点", code=BizCode.BAD_REQUEST)
        visited: set[uuid.UUID] = {node_id}
        current_id: uuid.UUID | None = new_parent_id
        while current_id is not None:
            if current_id in visited:
                raise BizException("移动后会产生循环引用", code=BizCode.BAD_REQUEST)
            visited.add(current_id)
            current_id = db.scalar(
                select(IntentNode.parent_id).where(
                    IntentNode.id == current_id,
                    IntentNode.user_id == user_id,
                )
            )

    def create(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        identifier: str,
        name: str,
        layer: str = IntentLayer.OTHER,
        kind: str = IntentKind.KB_RETRIEVE,
        parent_id: uuid.UUID | None = None,
        knowledge_base_id: uuid.UUID | None = None,
        description: str = "",
        examples: str = "",
        prompt_template: str | None = None,
        topic_k: int | None = None,
        sort: int = 0,
        enabled: bool = True,
    ) -> IntentNode:
        clean_identifier = self._validate_identifier(identifier)
        clean_name = self._validate_name(name)
        clean_layer = self._validate_layer(layer)
        clean_kind = self._validate_kind(kind)
        self._check_identifier_unique(db, user_id=user_id, identifier=clean_identifier)

        if parent_id is not None:
            # 校验父节点存在且属于当前用户
            self.get(db, user_id=user_id, node_id=parent_id)

        self._check_knowledge_base_owned(db, user_id=user_id, knowledge_base_id=knowledge_base_id)

        row = IntentNode(
            user_id=user_id,
            parent_id=parent_id,
            identifier=clean_identifier,
            name=clean_name,
            layer=clean_layer,
            kind=clean_kind,
            knowledge_base_id=knowledge_base_id,
            description=description.strip(),
            examples=examples.strip(),
            prompt_template=prompt_template.strip() if prompt_template else None,
            topic_k=topic_k,
            sort=sort,
            enabled=enabled,
        )
        db.add(row)
        db.flush()
        self._invalidate_cache(user_id)
        return row

    def get(self, db: Session, *, user_id: uuid.UUID, node_id: uuid.UUID) -> IntentNode:
        row = db.scalar(
            select(IntentNode).where(
                IntentNode.id == node_id,
                IntentNode.user_id == user_id,
            )
        )
        if row is None:
            raise BizException("意图节点不存在", code=BizCode.NOT_FOUND)
        return row

    def update(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        node_id: uuid.UUID,
        identifier: str | None = None,
        name: str | None = None,
        layer: str | None = None,
        kind: str | None = None,
        parent_id: object = _UNSET,
        knowledge_base_id: object = _UNSET,
        description: str | None = None,
        examples: str | None = None,
        prompt_template: object = _UNSET,
        topic_k: object = _UNSET,
        sort: int | None = None,
        enabled: bool | None = None,
    ) -> IntentNode:
        row = self.get(db, user_id=user_id, node_id=node_id)

        if identifier is not None:
            clean_identifier = self._validate_identifier(identifier)
            self._check_identifier_unique(
                db, user_id=user_id, identifier=clean_identifier, exclude_id=row.id
            )
            row.identifier = clean_identifier

        if name is not None:
            row.name = self._validate_name(name)

        if layer is not None:
            row.layer = self._validate_layer(layer)

        if kind is not None:
            row.kind = self._validate_kind(kind)

        if parent_id is not _UNSET:
            new_parent = parent_id if isinstance(parent_id, uuid.UUID) else None
            if new_parent is not None:
                # 校验父节点存在且属于当前用户
                self.get(db, user_id=user_id, node_id=new_parent)
                self._check_cycle(db, user_id=user_id, node_id=row.id, new_parent_id=new_parent)
            row.parent_id = new_parent

        if knowledge_base_id is not _UNSET:
            new_kb = knowledge_base_id if isinstance(knowledge_base_id, uuid.UUID) else None
            self._check_knowledge_base_owned(db, user_id=user_id, knowledge_base_id=new_kb)
            row.knowledge_base_id = new_kb

        if description is not None:
            row.description = description.strip()

        if examples is not None:
            row.examples = examples.strip()

        if prompt_template is not _UNSET:
            row.prompt_template = (
                prompt_template.strip()
                if isinstance(prompt_template, str) and prompt_template.strip()
                else None
            )

        if topic_k is not _UNSET:
            row.topic_k = topic_k if isinstance(topic_k, int) else None

        if sort is not None:
            row.sort = sort

        if enabled is not None:
            row.enabled = enabled

        db.flush()
        self._invalidate_cache(user_id)
        return row

    def delete(self, db: Session, *, user_id: uuid.UUID, node_id: uuid.UUID) -> None:
        row = self.get(db, user_id=user_id, node_id=node_id)
        has_children = db.scalar(
            select(func.count())
            .select_from(IntentNode)
            .where(
                IntentNode.parent_id == row.id,
                IntentNode.user_id == user_id,
            )
        )
        if has_children:
            raise BizException("该意图节点仍有子节点，无法删除", code=BizCode.CONFLICT)
        db.delete(row)
        db.flush()
        self._invalidate_cache(user_id)

    def list_nodes(self, db: Session, *, user_id: uuid.UUID) -> list[IntentNode]:
        """按 sort 升序、id 升序返回该用户所有意图节点。直接读库，不走缓存。"""
        return list(
            db.scalars(
                select(IntentNode)
                .where(IntentNode.user_id == user_id)
                .order_by(IntentNode.sort.asc(), IntentNode.id.asc())
            ).all()
        )

    def load_nodes(self, db: Session, *, user_id: uuid.UUID) -> list[IntentNode]:
        """读取该用户的整片意图森林，供检索等调用方传给意图分类。

        一个用户可以有多棵根树，它们放在同一条缓存里。键包含 user_id，
        不会读到其他租户的节点。未命中时回源数据库；没有节点时写入空标记。
        """
        cached = self._read_cache(user_id)
        if cached is not None:
            return cached
        nodes = self.list_nodes(db, user_id=user_id)
        self._write_cache(user_id, nodes)
        return nodes

    def _read_cache(self, user_id: uuid.UUID) -> list[IntentNode] | None:
        if self._redis is None:
            return None
        try:
            cached = self._redis.get(self._cache_key(user_id))
            if cached is None:
                return None
            data = json.loads(cached)
        except Exception as exc:
            logger.warning("读取 Redis 意图树缓存失败 user_id=%s: %s", user_id, exc)
            return None
        if isinstance(data, dict) and data.get(EMPTY_CACHE_SENTINEL):
            return []
        nodes = _nodes_from_cache(data)
        if nodes is None:
            logger.warning("Redis 意图树缓存格式无效 user_id=%s", user_id)
            return None
        return nodes

    def _write_cache(self, user_id: uuid.UUID, nodes: list[IntentNode]) -> None:
        if self._redis is None:
            return
        try:
            if not nodes:
                payload = json.dumps({EMPTY_CACHE_SENTINEL: True})
            else:
                payload = json.dumps([_dump_node(node) for node in nodes])
            self._redis.set(self._cache_key(user_id), payload, ex=CACHE_TTL_SECONDS)
        except Exception as exc:
            logger.warning("写入 Redis 意图树缓存失败 user_id=%s: %s", user_id, exc)


def _dump_node(node: IntentNode) -> dict[str, object]:
    return {
        "id": str(node.id),
        "user_id": str(node.user_id),
        "parent_id": None if node.parent_id is None else str(node.parent_id),
        "identifier": node.identifier,
        "name": node.name,
        "layer": node.layer,
        "kind": node.kind,
        "knowledge_base_id": None
        if node.knowledge_base_id is None
        else str(node.knowledge_base_id),
        "description": node.description,
        "examples": node.examples,
        "prompt_template": node.prompt_template,
        "topic_k": node.topic_k,
        "sort": node.sort,
        "enabled": node.enabled,
    }


def _nodes_from_cache(data: object) -> list[IntentNode] | None:
    if not isinstance(data, list):
        return None
    nodes: list[IntentNode] = []
    for item in data:
        node = _node_from_cache(item)
        if node is None:
            return None
        nodes.append(node)
    return nodes


def _node_from_cache(item: object) -> IntentNode | None:
    if not isinstance(item, dict):
        return None
    try:
        parent_id = item.get("parent_id")
        knowledge_base_id = item.get("knowledge_base_id")
        return IntentNode(
            id=uuid.UUID(str(item["id"])),
            user_id=uuid.UUID(str(item["user_id"])),
            parent_id=uuid.UUID(str(parent_id)) if parent_id else None,
            identifier=str(item["identifier"]),
            name=str(item["name"]),
            layer=str(item["layer"]),
            kind=str(item["kind"]),
            knowledge_base_id=uuid.UUID(str(knowledge_base_id)) if knowledge_base_id else None,
            description=str(item.get("description") or ""),
            examples=str(item.get("examples") or ""),
            prompt_template=item.get("prompt_template")
            if isinstance(item.get("prompt_template"), str)
            else None,
            topic_k=item.get("topic_k") if isinstance(item.get("topic_k"), int) else None,
            sort=int(item.get("sort") or 0),
            enabled=bool(item.get("enabled", True)),
        )
    except (KeyError, TypeError, ValueError):
        return None
