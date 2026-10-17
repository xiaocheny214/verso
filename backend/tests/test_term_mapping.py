"""查询术语归一化 CRUD 与缓存管理测试。

覆盖场景：
- CRUD 流程（创建、读取、更新、删除、分页、keyword 过滤）
- source_term 租户内唯一性约束校验与冲突处理
- 长词优先排序与替换规则（如“向量” vs “向量数据库”）
- priority 优先级生效顺序
- Redis 缓存：首次读取写入、命中缓存、增删改主动失效
- 防缓存击穿/穿透：空配置写入 sentinel，再次读取直接命中空列表而不查 DB
- 跨租户 404 / 越权保护
- HTTP REST API 端到端测试
"""

from collections.abc import Iterator

import pytest
from fakes import FakeRedis
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.bootstrap.app import create_app
from verso_app.server.auth.models import User
from verso_app.server.term_mapping.service import (
    CACHE_KEY_PREFIX,
    EMPTY_CACHE_SENTINEL,
    QueryTermMappingService,
)
from verso_app.web.middleware.auth import (
    get_current_user,
    get_session,
    get_term_mapping_service,
)
from verso_common.enums import BizCode, UserStatus
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


def _user(db: Session, token: str = "token-user") -> User:
    user = User(
        zhihu_url_token=token,
        display_name=token,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    return user


def test_crud_and_listing(db: Session) -> None:
    user = _user(db, "u1")
    service = QueryTermMappingService(db)

    # 1. 创建映射
    m1 = service.create(
        user_id=user.id,
        source_term="大模型",
        target_term="大型语言模型",
        priority=10,
        remark="简称展开",
    )
    assert m1.id is not None
    assert m1.source_term == "大模型"
    assert m1.target_term == "大型语言模型"
    assert m1.priority == 10
    assert m1.enabled is True

    # 2. 单条查询
    got = service.get(user_id=user.id, mapping_id=m1.id)
    assert got.id == m1.id
    assert got.remark == "简称展开"

    # 3. 更新
    updated = service.update(
        user_id=user.id,
        mapping_id=m1.id,
        target_term="LLM (大模型)",
        priority=20,
        enabled=False,
    )
    assert updated.target_term == "LLM (大模型)"
    assert updated.priority == 20
    assert updated.enabled is False

    # 4. 再次创建一条
    m2 = service.create(
        user_id=user.id,
        source_term="向量库",
        target_term="向量数据库",
        priority=5,
    )

    # 5. 列表与过滤
    items, total = service.list_mappings(user_id=user.id, page=1, page_size=10)
    assert total == 2
    assert len(items) == 2
    # 按 priority 降序：m1 (priority=20), m2 (priority=5)
    assert items[0].id == m1.id
    assert items[1].id == m2.id

    # 按 keyword 过滤
    items_filtered, total_filtered = service.list_mappings(user_id=user.id, keyword="向量")
    assert total_filtered == 1
    assert items_filtered[0].id == m2.id

    # 按 enabled 过滤
    items_enabled, total_enabled = service.list_mappings(user_id=user.id, enabled=True)
    assert total_enabled == 1
    assert items_enabled[0].id == m2.id

    # 6. 删除
    service.delete(user_id=user.id, mapping_id=m1.id)
    with pytest.raises(BizException) as exc_info:
        service.get(user_id=user.id, mapping_id=m1.id)
    assert exc_info.value.code == BizCode.NOT_FOUND


def test_source_term_unique_per_user(db: Session) -> None:
    u1 = _user(db, "u1")
    u2 = _user(db, "u2")
    service = QueryTermMappingService(db)

    # u1 创建“向量”映射
    service.create(user_id=u1.id, source_term="向量", target_term="Embedding")

    # u1 重复创建“向量”应冲突
    with pytest.raises(BizException) as exc:
        service.create(user_id=u1.id, source_term="向量", target_term="Vector")
    assert exc.value.code == BizCode.CONFLICT

    # u2 创建同样的“向量”应成功（租户隔离）
    m_u2 = service.create(user_id=u2.id, source_term="向量", target_term="向量检索")
    assert m_u2.user_id == u2.id


def test_long_term_priority_and_normalization(db: Session) -> None:
    """测试长词优先与 priority 优先级规则下的文本归一化。"""
    user = _user(db, "u1")
    service = QueryTermMappingService(db)

    # 场景 1：相同优先级下，长词优先（func.length(source_term).desc()）
    # 如果不先替换“向量数据库”，直接替换“向量”，则“向量数据库”会变成“Embedding数据库”从而导致“向量数据库”规则匹配失效
    service.create(
        user_id=user.id,
        source_term="向量",
        target_term="Vector",
        priority=0,
    )
    service.create(
        user_id=user.id,
        source_term="向量数据库",
        target_term="VectorDB",
        priority=0,
    )

    text = "我正在学习向量数据库以及向量检索技术"
    normalized = service.normalize(text, user_id=user.id)
    # “向量数据库”应当先被替换为 VectorDB，然后剩下的“向量”被替换为 Vector
    assert normalized == "我正在学习VectorDB以及Vector检索技术"

    # 场景 2：不同优先级下，高 priority 优先
    # 增加一条更高优先级的短词规则
    service.create(
        user_id=user.id,
        source_term="技术",
        target_term="科技",
        priority=100,
    )
    normalized2 = service.normalize(text, user_id=user.id)
    assert normalized2 == "我正在学习VectorDB以及Vector检索科技"


def test_disabled_term_not_normalized(db: Session) -> None:
    user = _user(db, "u1")
    service = QueryTermMappingService(db)

    service.create(
        user_id=user.id,
        source_term="RAG",
        target_term="检索增强生成",
        enabled=False,
    )

    text = "RAG 技术在 AI 领域的应用"
    assert service.normalize(text, user_id=user.id) == text


def test_non_contains_match_type_is_skipped(db: Session) -> None:
    user = _user(db, "u1")
    service = QueryTermMappingService(db)
    service.create(
        user_id=user.id,
        source_term="kodo",
        target_term="对象存储",
        match_type=2,
    )

    assert service.normalize("kodo如何配置", user_id=user.id) == "kodo如何配置"


def test_redis_cache_and_invalidation(db: Session) -> None:
    user = _user(db, "u1")
    redis = FakeRedis()
    service = QueryTermMappingService(db, redis=redis)
    cache_key = f"{CACHE_KEY_PREFIX}{user.id}"

    # 首次 load_mappings：由于没有任何规则，写入防击穿/防穿透空标记
    mappings = service.load_mappings(user.id)
    assert mappings == []
    assert cache_key in redis.values
    assert EMPTY_CACHE_SENTINEL in redis.values[cache_key]

    # 命中空标记缓存
    mappings_cached = service.load_mappings(user.id)
    assert mappings_cached == []

    # 创建一条新规则：必须使缓存失效
    m = service.create(
        user_id=user.id,
        source_term="大模型",
        target_term="LLM",
    )
    assert cache_key not in redis.values

    # 重新加载：读取 DB 并写入真实缓存
    mappings_new = service.load_mappings(user.id)
    assert len(mappings_new) == 1
    assert mappings_new[0]["source_term"] == "大模型"
    assert cache_key in redis.values

    # 更新规则：失效缓存
    service.update(user_id=user.id, mapping_id=m.id, target_term="Large Language Model")
    assert cache_key not in redis.values

    # 重新加载验证更新
    mappings_updated = service.load_mappings(user.id)
    assert mappings_updated[0]["target_term"] == "Large Language Model"
    assert cache_key in redis.values

    # 删除规则：失效缓存
    service.delete(user_id=user.id, mapping_id=m.id)
    assert cache_key not in redis.values


def test_tenant_isolation_and_404(db: Session) -> None:
    u1 = _user(db, "u1")
    u2 = _user(db, "u2")
    service = QueryTermMappingService(db)

    m1 = service.create(
        user_id=u1.id,
        source_term="测试词",
        target_term="目标词",
    )

    # u2 尝试读取 u1 的映射 -> NOT_FOUND
    with pytest.raises(BizException) as exc:
        service.get(user_id=u2.id, mapping_id=m1.id)
    assert exc.value.code == BizCode.NOT_FOUND

    # u2 尝试修改 u1 的映射 -> NOT_FOUND
    with pytest.raises(BizException) as exc:
        service.update(user_id=u2.id, mapping_id=m1.id, target_term="篡改")
    assert exc.value.code == BizCode.NOT_FOUND

    # u2 尝试删除 u1 的映射 -> NOT_FOUND
    with pytest.raises(BizException) as exc:
        service.delete(user_id=u2.id, mapping_id=m1.id)
    assert exc.value.code == BizCode.NOT_FOUND


def test_api_endpoints(db: Session) -> None:
    u1 = _user(db, "u1")
    u2 = _user(db, "u2")
    fake_redis = FakeRedis()

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: u1
    app.dependency_overrides[get_term_mapping_service] = lambda: QueryTermMappingService(
        db, redis=fake_redis
    )

    client = TestClient(app)

    # 1. POST /me/term-mappings
    res = client.post(
        "/me/term-mappings",
        json={
            "source_term": "向量数据库",
            "target_term": "VectorDB",
            "priority": 10,
            "remark": "专业术语",
        },
    )
    assert res.status_code == 200
    data = res.json()["data"]
    mapping_id = data["id"]
    assert data["source_term"] == "向量数据库"
    assert data["target_term"] == "VectorDB"
    assert data["priority"] == 10
    assert data["remark"] == "专业术语"

    # 2. GET /me/term-mappings/{id}
    res_get = client.get(f"/me/term-mappings/{mapping_id}")
    assert res_get.status_code == 200
    assert res_get.json()["data"]["id"] == mapping_id

    # 3. PATCH /me/term-mappings/{id}
    res_patch = client.patch(
        f"/me/term-mappings/{mapping_id}",
        json={"target_term": "Milvus", "enabled": False},
    )
    assert res_patch.status_code == 200
    assert res_patch.json()["data"]["target_term"] == "Milvus"
    assert res_patch.json()["data"]["enabled"] is False

    # 4. GET /me/term-mappings (列表与分页)
    res_list = client.get("/me/term-mappings?page=1&page_size=10")
    assert res_list.status_code == 200
    list_body = res_list.json()
    assert list_body["total"] == 1
    assert len(list_body["data"]) == 1
    assert list_body["data"][0]["id"] == mapping_id

    # 5. 跨租户防护：切换到 u2
    app.dependency_overrides[get_current_user] = lambda: u2
    res_u2_get = client.get(f"/me/term-mappings/{mapping_id}")
    assert res_u2_get.status_code == 200
    assert res_u2_get.json()["code"] == BizCode.NOT_FOUND

    res_u2_list = client.get("/me/term-mappings")
    assert res_u2_list.status_code == 200
    assert res_u2_list.json()["total"] == 0

    # 6. DELETE /me/term-mappings/{id} 作为 u1 恢复并删除
    app.dependency_overrides[get_current_user] = lambda: u1
    res_del = client.delete(f"/me/term-mappings/{mapping_id}")
    assert res_del.status_code == 200

    res_after_del = client.get(f"/me/term-mappings/{mapping_id}")
    assert res_after_del.json()["code"] == BizCode.NOT_FOUND
