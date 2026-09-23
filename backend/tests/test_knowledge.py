from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.bootstrap.app import create_app
from verso_app.server.article.models import UserArticle
from verso_app.server.article.service import ArchiveService
from verso_app.server.auth.models import User
from verso_app.server.knowledge.migration import ensure_knowledge_schema
from verso_app.server.knowledge.models import KnowledgeBase
from verso_app.server.knowledge.service import KnowledgeService
from verso_app.web.middleware.auth import get_current_user, get_session
from verso_common.enums import BizCode, UserStatus
from verso_common.exceptions import BizException
from verso_framework.db.base import Base
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
    assert created.collection == "verso_chunks"
    assert service.list(db, user_id=owner.id) == [created]

    updated = service.update(db, user_id=owner.id, knowledge_base_id=created.id, name="Notes")
    assert updated.name == "Notes"

    with pytest.raises(BizException) as exc:
        service.get(db, user_id=outsider.id, knowledge_base_id=created.id)
    assert exc.value.code == BizCode.NOT_FOUND

    service.delete(db, user_id=owner.id, knowledge_base_id=created.id)
    assert service.list(db, user_id=owner.id) == []


def test_knowledge_base_delete_rejects_non_empty_base(db: Session) -> None:
    service = KnowledgeService()
    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    knowledge_base = service.create(db, user_id=user.id, name="Writing")

    archive.put_markdown(
        db,
        user_id=user.id,
        knowledge_base_id=knowledge_base.id,
        source_url="https://zhuanlan.zhihu.com/p/1",
        data=b"# article",
        content_type="article",
    )

    with pytest.raises(BizException) as exc:
        service.delete(db, user_id=user.id, knowledge_base_id=knowledge_base.id)
    assert exc.value.code == BizCode.CONFLICT
    assert db.get(KnowledgeBase, knowledge_base.id) is not None


def test_user_without_articles_has_no_default_base(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)

    assert service.list(db, user_id=user.id) == []


def test_archive_rejects_another_users_knowledge_base(db: Session) -> None:
    service = KnowledgeService()
    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    owner = _user(db)
    outsider = _user(db, token="token-b")
    knowledge_base = service.create(db, user_id=owner.id, name="Writing")

    with pytest.raises(BizException) as exc:
        archive.put_markdown(
            db,
            user_id=outsider.id,
            knowledge_base_id=knowledge_base.id,
            source_url="https://zhuanlan.zhihu.com/p/other-user",
            data=b"forbidden",
            content_type="article",
        )
    assert exc.value.code == BizCode.NOT_FOUND


def test_archive_uses_default_base_and_scopes_article_reads(db: Session) -> None:
    service = KnowledgeService()
    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    other_base = service.create(db, user_id=user.id, name="Other")

    default_row = archive.put_markdown(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/default",
        data=b"default",
        content_type="article",
    )
    other_row = archive.put_markdown(
        db,
        user_id=user.id,
        knowledge_base_id=other_base.id,
        source_url="https://zhuanlan.zhihu.com/p/other",
        data=b"other",
        content_type="article",
    )

    default_base = db.get(KnowledgeBase, default_row.knowledge_base_id)
    assert default_base is not None
    assert default_base.name == "Default"
    assert default_row.knowledge_base_id != other_row.knowledge_base_id
    assert [
        row.source_url
        for row in archive.list_by_knowledge_base(
            db, user_id=user.id, knowledge_base_id=default_base.id
        )
    ] == ["https://zhuanlan.zhihu.com/p/default"]
    assert [
        row.source_url
        for row in archive.list_by_knowledge_base(
            db, user_id=user.id, knowledge_base_id=other_base.id
        )
    ] == ["https://zhuanlan.zhihu.com/p/other"]


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

    listed = client.get("/me/knowledge-bases")
    assert [item["name"] for item in listed.json()["data"]] == ["Writing"]

    app.dependency_overrides[get_current_user] = lambda: outsider
    hidden = client.get(f"/me/knowledge-bases/{knowledge_base_id}")
    assert hidden.json()["code"] == BizCode.NOT_FOUND

    app.dependency_overrides.clear()


def test_legacy_article_rows_can_be_backfilled_to_default_base(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)
    engine = db.get_bind()
    db.commit()
    Base.metadata.drop_all(engine, tables=[UserArticle.__table__])
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
                    (id, user_id, source_url, content_type, title, object_key, status,
                     created_at, updated_at)
                VALUES
                    (:id, :user_id, :source_url, 'article', 'legacy', 'articles/legacy',
                     'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": "f" * 32,
                "user_id": user.id.hex,
                "source_url": "https://zhuanlan.zhihu.com/p/legacy",
            },
        )

    ensure_knowledge_schema(engine)

    row = db.get(UserArticle, uuid.UUID("f" * 32))
    assert row is not None
    assert row.knowledge_base_id is not None
    assert service.list(db, user_id=user.id)[0].name == "Default"
