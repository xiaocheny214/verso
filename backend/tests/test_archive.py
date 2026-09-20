from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.server.article.keys import article_object_key
from verso_app.server.article.models import UserArticle
from verso_app.server.article.service import ArchiveService
from verso_app.server.auth.models import User
from verso_common.enums import ArticleStatus, UserStatus
from verso_framework.db.base import Base
from verso_framework.storage import MemoryObjectStore, ObjectStoreError
from verso_framework.storage.ports import StoredObject


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


def _user(db: Session) -> User:
    user = User(
        zhihu_url_token="token-a",
        display_name="A",
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    return user


def test_put_get_delete_markdown(db: Session) -> None:
    store = MemoryObjectStore()
    archive = ArchiveService(store, key_prefix="articles")
    user = _user(db)
    url = "https://zhuanlan.zhihu.com/p/1"
    body = "# 标题\n正文".encode()

    row = archive.put_markdown(
        db,
        user_id=user.id,
        source_url=url,
        data=body,
        content_type="article",
        title="标题",
        summary="摘要",
        fetched_at=datetime(2026, 9, 20, tzinfo=UTC),
    )
    assert row.status == ArticleStatus.READY
    assert row.object_key == article_object_key(user.id, url)
    assert archive.get_markdown(db, user_id=user.id, source_url=url) == body
    listed = archive.list_by_user(db, user_id=user.id)
    assert len(listed) == 1
    assert listed[0].title == "标题"
    assert archive.delete(db, user_id=user.id, source_url=url) is True
    assert archive.get_by_source(db, user_id=user.id, source_url=url) is None
    assert store.exists(row.object_key) is False


def test_same_url_upserts_and_skips_unchanged_body(db: Session) -> None:
    store = MemoryObjectStore()
    archive = ArchiveService(store, key_prefix="articles")
    user = _user(db)
    url = "https://www.zhihu.com/answer/1"
    first = archive.put_markdown(
        db,
        user_id=user.id,
        source_url=url,
        data=b"one",
        content_type="answer",
        title="一",
    )
    second = archive.put_markdown(
        db,
        user_id=user.id,
        source_url=url,
        data=b"one",
        content_type="answer",
        title="一改",
    )
    assert first.id == second.id
    assert db.scalar(select(UserArticle).where(UserArticle.user_id == user.id)) is second
    assert archive.get_markdown(db, user_id=user.id, source_url=url) == b"one"

    third = archive.put_markdown(
        db,
        user_id=user.id,
        source_url=url,
        data=b"two",
        content_type="answer",
        title="二",
    )
    assert third.id == first.id
    assert archive.get_markdown(db, user_id=user.id, source_url=url) == b"two"


def test_put_failure_marks_row_failed(db: Session) -> None:
    class BoomStore(MemoryObjectStore):
        def put(
            self, key: str, data: bytes, *, content_type: str = "text/markdown"
        ) -> StoredObject:
            raise ObjectStoreError("boom")

    archive = ArchiveService(BoomStore(), key_prefix="articles")
    user = _user(db)
    url = "https://zhuanlan.zhihu.com/p/2"
    with pytest.raises(ObjectStoreError):
        archive.put_markdown(
            db,
            user_id=user.id,
            source_url=url,
            data=b"x",
            content_type="article",
            title="x",
        )
    row = archive.get_by_source(db, user_id=user.id, source_url=url)
    assert row is not None
    assert row.status == ArticleStatus.FAILED
    assert row.error_class == "object_store_put"
