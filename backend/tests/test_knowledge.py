from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.bootstrap.app import create_app
from verso_app.server.auth.models import User
from verso_app.server.collect.models import ArticleCollectionRecord
from verso_app.server.collect.service import CollectService
from verso_app.server.knowledge.models import KnowledgeBase
from verso_app.server.knowledge.service import KnowledgeService
from verso_app.web.middleware.auth import get_current_user, get_session
from verso_common.enums import BizCode, UserStatus
from verso_common.exceptions import BizException
from verso_framework.db.base import Base
from verso_framework.db.migrations import run_pending_migrations
from verso_framework.storage import MemoryObjectStore


@pytest.fixture
def db() -> Session:
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


def test_knowledge_base_crud_is_scoped_to_owner(db: Session) -> None:
    service = KnowledgeService()
    owner = _user(db)
    outsider = _user(db, token="token-b")

    created = service.create(db, user_id=owner.id, name="Writing")
    assert created.name == "Writing"
    assert created.embedding_model == ""
    assert created.collection_name == "writing"
    assert service.list(db, user_id=owner.id) == [created]

    updated = service.update(db, user_id=owner.id, knowledge_base_id=created.id, name="Notes")
    assert updated.name == "Notes"

    with pytest.raises(BizException) as exc:
        service.get(db, user_id=outsider.id, knowledge_base_id=created.id)
    assert exc.value.code == BizCode.NOT_FOUND

    service.delete(db, user_id=owner.id, knowledge_base_id=created.id)
    assert service.list(db, user_id=owner.id) == []


def test_knowledge_base_accepts_owner_collection_name(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)

    created = service.create(db, user_id=user.id, name="Essays", collection_name="My_Notes")
    assert created.collection_name == "my_notes"
    assert created.embedding_model == ""

    default_base = service.get_or_create_default(db, user_id=user.id)
    assert default_base.collection_name == "default"

    updated = service.update(
        db,
        user_id=user.id,
        knowledge_base_id=created.id,
        collection_name="essays_v2",
    )
    assert updated.collection_name == "essays_v2"


def test_knowledge_base_rejects_duplicate_or_invalid_collection_name(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)
    service.create(db, user_id=user.id, name="Writing", collection_name="notes")

    with pytest.raises(BizException) as duplicate:
        service.create(db, user_id=user.id, name="Other", collection_name="notes")
    assert duplicate.value.code == BizCode.CONFLICT

    with pytest.raises(BizException) as invalid:
        service.create(db, user_id=user.id, name="Bad", collection_name="1notes")
    assert invalid.value.code == BizCode.BAD_REQUEST


def test_knowledge_routes_store_collection_name_and_ignore_embedding(db: Session) -> None:
    owner = _user(db)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)

    created = client.post(
        "/me/knowledge-bases",
        json={
            "name": "Writing",
            "collection_name": "essays",
            "embedding_model": "other-embed",
        },
    )
    assert created.json()["code"] == BizCode.SUCCESS
    assert created.json()["data"]["collection_name"] == "essays"
    assert created.json()["data"]["embedding_model"] == ""
    knowledge_base_id = created.json()["data"]["id"]

    patched = client.patch(
        f"/me/knowledge-bases/{knowledge_base_id}",
        json={"collection_name": "drafts", "embedding_model": "still-ignored"},
    )
    assert patched.json()["code"] == BizCode.SUCCESS
    assert patched.json()["data"]["collection_name"] == "drafts"
    assert patched.json()["data"]["embedding_model"] == ""

    app.dependency_overrides.clear()


def test_knowledge_base_delete_ignores_collection_records(db: Session) -> None:
    service = KnowledgeService()
    archive = CollectService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    knowledge_base = service.create(db, user_id=user.id, name="Writing")

    archive.put_markdown(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/1",
        data=b"# article",
        content_type="article",
    )

    service.delete(db, user_id=user.id, knowledge_base_id=knowledge_base.id)
    assert db.get(KnowledgeBase, knowledge_base.id) is None


def test_collection_record_does_not_require_knowledge_base(db: Session) -> None:
    archive = CollectService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)

    row = archive.put_markdown(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/default",
        data=b"default",
        content_type="article",
        summary="a zhihu piece",
    )

    assert row.description == "a zhihu piece"
    assert not hasattr(row, "knowledge_base_id")
    assert [item.source_url for item in archive.list_by_user(db, user_id=user.id)] == [
        "https://zhuanlan.zhihu.com/p/default"
    ]


def test_user_without_articles_has_no_default_base(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)

    assert service.list(db, user_id=user.id) == []


def test_knowledge_routes_return_owner_scoped_data(db: Session) -> None:
    owner = _user(db)
    outsider = _user(db, token="token-b")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)

    created = client.post("/me/knowledge-bases", json={"name": "Writing"})
    assert created.json()["code"] == BizCode.SUCCESS
    knowledge_base_id = created.json()["data"]["id"]
    assert created.json()["data"]["collection_name"] == "writing"
    assert created.json()["data"]["embedding_model"] == ""

    listed = client.get("/me/knowledge-bases")
    assert [item["name"] for item in listed.json()["data"]] == ["Writing"]

    app.dependency_overrides[get_current_user] = lambda: outsider
    hidden = client.get(f"/me/knowledge-bases/{knowledge_base_id}")
    assert hidden.json()["code"] == BizCode.NOT_FOUND

    app.dependency_overrides.clear()


def test_legacy_user_articles_rename_to_collection_records(db: Session) -> None:
    user = _user(db)
    engine = db.get_bind()
    db.commit()
    Base.metadata.drop_all(engine, tables=[ArticleCollectionRecord.__table__])
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE user_articles (
                    id CHAR(32) PRIMARY KEY,
                    user_id CHAR(32) NOT NULL,
                    source_url TEXT NOT NULL,
                    content_type VARCHAR(32) NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    object_key TEXT NOT NULL UNIQUE,
                    content_hash VARCHAR(64),
                    byte_size INTEGER,
                    status VARCHAR(16) NOT NULL,
                    error_class VARCHAR(64),
                    fetched_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT user_articles_user_source_url UNIQUE (user_id, source_url)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO user_articles
                    (id, user_id, source_url, content_type, title, summary, object_key, status,
                     created_at, updated_at)
                VALUES
                    (:id, :user_id, :source_url, 'article', 'legacy', 'from zhihu',
                     'articles/legacy', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": "f" * 32,
                "user_id": user.id.hex,
                "source_url": "https://zhuanlan.zhihu.com/p/legacy",
            },
        )

    run_pending_migrations(engine)
    run_pending_migrations(engine)

    row = db.get(ArticleCollectionRecord, uuid.UUID("f" * 32))
    assert row is not None
    assert row.title == "legacy"
    assert row.description == "from zhihu"
    assert row.source_url == "https://zhuanlan.zhihu.com/p/legacy"
    assert db.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one() == 1
