"""当前用户意图节点与意图树装配路由。"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from verso_app.server.auth.models import User
from verso_app.server.intent.models import IntentNode
from verso_app.server.intent.service import _UNSET, IntentService
from verso_app.web.middleware.auth import SessionDep, get_current_user
from verso_common.models import IntentForestView, IntentNodeView, IntentTreeView
from verso_common.result import Response as ApiResponse

router = APIRouter(tags=["intent"])

IntentDep = Annotated[IntentService, Depends(IntentService)]
UserDep = Annotated[User, Depends(get_current_user)]


class IntentNodeCreateBody(BaseModel):
    identifier: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    layer: str = Field(default="other", max_length=16)
    kind: str = Field(default="kb_retrieve", max_length=32)
    parent_id: uuid.UUID | None = None
    knowledge_base_id: uuid.UUID | None = None
    description: str = ""
    examples: str = ""
    prompt_template: str | None = None
    topic_k: int | None = None
    sort: int = 0
    enabled: bool = True


class IntentNodePatchBody(BaseModel):
    identifier: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    layer: str | None = Field(default=None, max_length=16)
    kind: str | None = Field(default=None, max_length=32)
    parent_id: uuid.UUID | None = None
    knowledge_base_id: uuid.UUID | None = None
    description: str | None = None
    examples: str | None = None
    prompt_template: str | None = None
    topic_k: int | None = None
    sort: int | None = None
    enabled: bool | None = None


def _node_view(row: IntentNode) -> IntentNodeView:
    return IntentNodeView(
        id=str(row.id),
        parent_id=str(row.parent_id) if row.parent_id is not None else None,
        identifier=row.identifier,
        name=row.name,
        layer=row.layer,
        kind=row.kind,
        knowledge_base_id=str(row.knowledge_base_id) if row.knowledge_base_id is not None else None,
        description=row.description,
        examples=row.examples,
        prompt_template=row.prompt_template,
        topic_k=row.topic_k,
        sort=row.sort,
        enabled=row.enabled,
    )


def _node_tree_view(row: IntentNode) -> IntentTreeView:
    return IntentTreeView(
        id=str(row.id),
        parent_id=str(row.parent_id) if row.parent_id is not None else None,
        identifier=row.identifier,
        name=row.name,
        layer=row.layer,
        kind=row.kind,
        knowledge_base_id=str(row.knowledge_base_id) if row.knowledge_base_id is not None else None,
        description=row.description,
        examples=row.examples,
        prompt_template=row.prompt_template,
        topic_k=row.topic_k,
        sort=row.sort,
        enabled=row.enabled,
        children=[],
    )


def _build_forest(nodes: list[IntentNode]) -> list[IntentTreeView]:
    """将已按 sort、id 排序的节点装配为嵌套森林，保持兄弟节点排序。"""
    views = {str(node.id): _node_tree_view(node) for node in nodes}
    roots: list[IntentTreeView] = []

    for node in nodes:
        view = views[str(node.id)]
        if node.parent_id is None:
            roots.append(view)
        else:
            parent_view = views.get(str(node.parent_id))
            if parent_view is not None:
                parent_view.children.append(view)
            else:
                # 异常容错：若父节点不存在，回退为根节点输出
                roots.append(view)

    return roots


@router.get("/me/intent-trees")
def list_intent_trees(
    session: SessionDep,
    intent: IntentDep,
    user: UserDep,
) -> ApiResponse[IntentForestView]:
    """返回服务端装配好的意图森林，兄弟节点按 sort、id 排序。"""
    nodes = intent.list_nodes(session, user_id=user.id)
    forest = _build_forest(nodes)
    return ApiResponse.success(IntentForestView(items=forest))


@router.post("/me/intent-nodes")
def create_intent_node(
    body: IntentNodeCreateBody,
    session: SessionDep,
    intent: IntentDep,
    user: UserDep,
) -> ApiResponse[IntentNodeView]:
    row = intent.create(
        session,
        user_id=user.id,
        identifier=body.identifier,
        name=body.name,
        layer=body.layer,
        kind=body.kind,
        parent_id=body.parent_id,
        knowledge_base_id=body.knowledge_base_id,
        description=body.description,
        examples=body.examples,
        prompt_template=body.prompt_template,
        topic_k=body.topic_k,
        sort=body.sort,
        enabled=body.enabled,
    )
    return ApiResponse.success(_node_view(row))


@router.get("/me/intent-nodes/{node_id}")
def get_intent_node(
    node_id: uuid.UUID,
    session: SessionDep,
    intent: IntentDep,
    user: UserDep,
) -> ApiResponse[IntentNodeView]:
    row = intent.get(session, user_id=user.id, node_id=node_id)
    return ApiResponse.success(_node_view(row))


@router.patch("/me/intent-nodes/{node_id}")
def patch_intent_node(
    node_id: uuid.UUID,
    body: IntentNodePatchBody,
    session: SessionDep,
    intent: IntentDep,
    user: UserDep,
) -> ApiResponse[IntentNodeView]:
    fields = body.model_fields_set
    row = intent.update(
        session,
        user_id=user.id,
        node_id=node_id,
        identifier=body.identifier if "identifier" in fields else None,
        name=body.name if "name" in fields else None,
        layer=body.layer if "layer" in fields else None,
        kind=body.kind if "kind" in fields else None,
        parent_id=body.parent_id if "parent_id" in fields else _UNSET,
        knowledge_base_id=body.knowledge_base_id if "knowledge_base_id" in fields else _UNSET,
        description=body.description if "description" in fields else None,
        examples=body.examples if "examples" in fields else None,
        prompt_template=body.prompt_template if "prompt_template" in fields else _UNSET,
        topic_k=body.topic_k if "topic_k" in fields else _UNSET,
        sort=body.sort if "sort" in fields else None,
        enabled=body.enabled if "enabled" in fields else None,
    )
    return ApiResponse.success(_node_view(row))


@router.delete("/me/intent-nodes/{node_id}")
def delete_intent_node(
    node_id: uuid.UUID,
    session: SessionDep,
    intent: IntentDep,
    user: UserDep,
) -> ApiResponse[None]:
    intent.delete(session, user_id=user.id, node_id=node_id)
    return ApiResponse.success()
