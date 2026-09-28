"""意图树与节点 CRUD 测试。

覆盖场景：
- 根节点与子节点创建、单节点查询、层级更新
- identifier 字母数字下划线校验与唯一性
- 树移动时的循环引用与自引用拦截
- 跨租户节点/知识库访问 404
- 存在子节点时拒绝删除父节点
- 嵌套意图森林（server-built forest）装配与兄弟节点排序
- 知识库删除保护：存在 enabled 意图节点时拒绝删除，禁用后允许删除
- HTTP API 端到端路由测试与租户隔离
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.bootstrap.app import create_app
from verso_app.server.auth.models import User
from verso_app.server.intent.models import IntentNode
from verso_app.server.intent.service import IntentService
from verso_app.server.knowledge.models import KnowledgeBase
from verso_app.server.knowledge.service import KnowledgeService
from verso_app.web.middleware.auth import get_current_user, get_session
from verso_common.enums import BizCode, IntentKind, IntentLayer, UserStatus
from verso_common.exceptions import BizException
from verso_framework.db.base import Base


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def _user(db: Session, token: str = "token-a") -> User:
    user = User(
        zhihu_url_token=token,
        display_name=token,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    return user


def _kb(db: Session, user: User, name: str = "TestKB") -> KnowledgeBase:
    kb_service = KnowledgeService()
    return kb_service.create(db, user_id=user.id, name=name)


def test_intent_node_create_and_get(db: Session) -> None:
    service = IntentService()
    owner = _user(db, "owner")
    outsider = _user(db, "outsider")
    kb = _kb(db, owner, "Architecture")

    node = service.create(
        db,
        user_id=owner.id,
        identifier="arch_domain",
        name="架构设计",
        layer=IntentLayer.DOMAIN,
        kind=IntentKind.KB_RETRIEVE,
        knowledge_base_id=kb.id,
        description="系统设计意图",
        examples="高并发方案",
        sort=10,
    )
    assert node.identifier == "arch_domain"
    assert node.name == "架构设计"
    assert node.layer == IntentLayer.DOMAIN
    assert node.kind == IntentKind.KB_RETRIEVE
    assert node.parent_id is None
    assert node.knowledge_base_id == kb.id
    assert node.enabled is True

    # 正常获取
    fetched = service.get(db, user_id=owner.id, node_id=node.id)
    assert fetched.id == node.id

    # 跨用户获取返回 404
    with pytest.raises(BizException) as exc:
        service.get(db, user_id=outsider.id, node_id=node.id)
    assert exc.value.code == BizCode.NOT_FOUND


def test_intent_node_identifier_validation(db: Session) -> None:
    service = IntentService()
    owner = _user(db, "owner")

    # 非法字符（包含横杠、空格、特殊符号）
    for invalid in ["arch-domain", "arch domain", "arch@node", "", "  "]:
        with pytest.raises(BizException) as exc:
            service.create(db, user_id=owner.id, identifier=invalid, name="测试")
        assert exc.value.code == BizCode.BAD_REQUEST

    # 合法字符（大小写字母、数字、下划线）
    valid_node = service.create(
        db, user_id=owner.id, identifier="Arch_Domain_123", name="合法标识符"
    )
    assert valid_node.identifier == "Arch_Domain_123"


def test_intent_node_identifier_unique_per_user(db: Session) -> None:
    service = IntentService()
    owner1 = _user(db, "owner1")
    owner2 = _user(db, "owner2")

    service.create(db, user_id=owner1.id, identifier="my_intent", name="意图1")

    # 同一用户冲突
    with pytest.raises(BizException) as exc:
        service.create(db, user_id=owner1.id, identifier="my_intent", name="意图2")
    assert exc.value.code == BizCode.CONFLICT

    # 不同用户允许相同标识符
    node2 = service.create(db, user_id=owner2.id, identifier="my_intent", name="意图2")
    assert node2.identifier == "my_intent"


def test_intent_node_parent_and_kb_tenant_isolation(db: Session) -> None:
    service = IntentService()
    owner = _user(db, "owner")
    outsider = _user(db, "outsider")

    outsider_node = service.create(db, user_id=outsider.id, identifier="outsider_node", name="外部")
    outsider_kb = _kb(db, outsider, "OutsiderKB")

    # 试图引用其他用户的节点作为父节点 -> 404
    with pytest.raises(BizException) as exc1:
        service.create(
            db,
            user_id=owner.id,
            identifier="child_node",
            name="子节点",
            parent_id=outsider_node.id,
        )
    assert exc1.value.code == BizCode.NOT_FOUND

    # 试图引用其他用户的知识库 -> 404
    with pytest.raises(BizException) as exc2:
        service.create(
            db,
            user_id=owner.id,
            identifier="kb_node",
            name="知识库节点",
            knowledge_base_id=outsider_kb.id,
        )
    assert exc2.value.code == BizCode.NOT_FOUND


def test_intent_node_cycle_prevention(db: Session) -> None:
    service = IntentService()
    owner = _user(db, "owner")

    # 构造链路：A -> B -> C
    node_a = service.create(db, user_id=owner.id, identifier="node_a", name="A")
    node_b = service.create(
        db, user_id=owner.id, identifier="node_b", name="B", parent_id=node_a.id
    )
    node_c = service.create(
        db, user_id=owner.id, identifier="node_c", name="C", parent_id=node_b.id
    )

    # 1. 尝试自引用：A 的 parent_id 设为 A
    with pytest.raises(BizException) as exc_self:
        service.update(db, user_id=owner.id, node_id=node_a.id, parent_id=node_a.id)
    assert exc_self.value.code == BizCode.BAD_REQUEST

    # 2. 尝试成环：A 的 parent_id 设为 C (A -> B -> C -> A)
    with pytest.raises(BizException) as exc_cycle:
        service.update(db, user_id=owner.id, node_id=node_a.id, parent_id=node_c.id)
    assert exc_cycle.value.code == BizCode.BAD_REQUEST

    # 3. 合法移动：将 C 移为根节点 (parent_id = None)
    updated_c = service.update(db, user_id=owner.id, node_id=node_c.id, parent_id=None)
    assert updated_c.parent_id is None

    # 4. 将 A 移至 C 下 (C -> A -> B)
    updated_a = service.update(db, user_id=owner.id, node_id=node_a.id, parent_id=node_c.id)
    assert updated_a.parent_id == node_c.id


def test_intent_node_delete_refuses_when_has_children(db: Session) -> None:
    service = IntentService()
    owner = _user(db, "owner")

    parent = service.create(db, user_id=owner.id, identifier="parent", name="父节点")
    child = service.create(
        db, user_id=owner.id, identifier="child", name="子节点", parent_id=parent.id
    )

    # 有子节点拒绝删除
    with pytest.raises(BizException) as exc:
        service.delete(db, user_id=owner.id, node_id=parent.id)
    assert exc.value.code == BizCode.CONFLICT

    # 删除子节点后，父节点可被删除
    service.delete(db, user_id=owner.id, node_id=child.id)
    service.delete(db, user_id=owner.id, node_id=parent.id)
    assert db.get(IntentNode, parent.id) is None


def test_knowledge_base_delete_protected_by_enabled_intent_node(db: Session) -> None:
    intent_service = IntentService()
    kb_service = KnowledgeService()
    owner = _user(db, "owner")
    kb = _kb(db, owner, "ProtectedKB")

    # 创建指向知识库的启用意图节点
    node = intent_service.create(
        db,
        user_id=owner.id,
        identifier="kb_intent",
        name="意图",
        knowledge_base_id=kb.id,
        enabled=True,
    )

    # 尝试删除知识库 -> 拒绝
    with pytest.raises(BizException) as exc:
        kb_service.delete(db, user_id=owner.id, knowledge_base_id=kb.id)
    assert exc.value.code == BizCode.CONFLICT
    assert "启用的意图节点" in exc.value.message

    # 将意图节点禁用
    intent_service.update(db, user_id=owner.id, node_id=node.id, enabled=False)

    # 禁用后可以顺利删除知识库
    kb_service.delete(db, user_id=owner.id, knowledge_base_id=kb.id)
    assert db.get(KnowledgeBase, kb.id) is None


def test_intent_trees_route_and_server_built_forest(db: Session) -> None:
    owner = _user(db, "owner")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)

    # 创建根节点 1 (sort=20)
    r1 = client.post(
        "/me/intent-nodes",
        json={"identifier": "root_2", "name": "后端技术", "sort": 20},
    ).json()["data"]

    # 创建根节点 2 (sort=10)
    client.post(
        "/me/intent-nodes",
        json={"identifier": "root_1", "name": "前端技术", "sort": 10},
    )

    # 在 root_2 下创建两个子节点
    c1 = client.post(
        "/me/intent-nodes",
        json={
            "identifier": "backend_db",
            "name": "数据库",
            "parent_id": r1["id"],
            "sort": 5,
        },
    ).json()["data"]

    client.post(
        "/me/intent-nodes",
        json={
            "identifier": "backend_mq",
            "name": "消息队列",
            "parent_id": r1["id"],
            "sort": 1,
        },
    )

    # 在 c1 下创建孙子节点
    client.post(
        "/me/intent-nodes",
        json={
            "identifier": "db_postgres",
            "name": "PostgreSQL",
            "parent_id": c1["id"],
            "sort": 0,
        },
    )

    # 获取服务端装配森林
    res = client.get("/me/intent-trees")
    assert res.status_code == 200
    forest = res.json()["data"]["items"]

    # 顶层应有两个根节点，且按 sort 升序：root_1(sort=10)在前，root_2(sort=20)在后
    assert len(forest) == 2
    assert forest[0]["identifier"] == "root_1"
    assert forest[1]["identifier"] == "root_2"

    # root_2 下应有两个子节点，按 sort 升序：backend_mq(sort=1)在前，backend_db(sort=5)在后
    r2_children = forest[1]["children"]
    assert len(r2_children) == 2
    assert r2_children[0]["identifier"] == "backend_mq"
    assert r2_children[1]["identifier"] == "backend_db"

    # backend_db 下应有孙子节点
    c1_children = r2_children[1]["children"]
    assert len(c1_children) == 1
    assert c1_children[0]["identifier"] == "db_postgres"

    # 单节点编辑表单查询 GET /me/intent-nodes/{id}
    single_res = client.get(f"/me/intent-nodes/{c1['id']}")
    assert single_res.status_code == 200
    assert single_res.json()["data"]["identifier"] == "backend_db"
    assert single_res.json()["data"]["parent_id"] == r1["id"]

    # 更新节点 PATCH
    patch_res = client.patch(
        f"/me/intent-nodes/{c1['id']}",
        json={"name": "存储与数据库", "description": "所有持久化存储"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["data"]["name"] == "存储与数据库"

    app.dependency_overrides.clear()


def test_intent_routes_cross_user_isolation(db: Session) -> None:
    owner = _user(db, "owner")
    outsider = _user(db, "outsider")
    app = create_app()

    # owner 创建节点
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)
    created = client.post(
        "/me/intent-nodes",
        json={"identifier": "secret_node", "name": "私密节点"},
    ).json()["data"]

    # outsider 尝试访问该节点 -> 404
    app.dependency_overrides[get_current_user] = lambda: outsider
    res_get = client.get(f"/me/intent-nodes/{created['id']}")
    assert res_get.json()["code"] == BizCode.NOT_FOUND

    # outsider 尝试修改 -> 404
    res_patch = client.patch(f"/me/intent-nodes/{created['id']}", json={"name": "非法修改"})
    assert res_patch.json()["code"] == BizCode.NOT_FOUND

    # outsider 尝试删除 -> 404
    res_del = client.delete(f"/me/intent-nodes/{created['id']}")
    assert res_del.json()["code"] == BizCode.NOT_FOUND

    app.dependency_overrides.clear()
