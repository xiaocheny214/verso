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


def test_enqueue_listed_contents_skips_pins(db: Session) -> None:
    from verso_framework.providers.zhihu import ZhihuContent

    article_url = "https://zhuanlan.zhihu.com/p/10"
    pin_url = "https://www.zhihu.com/pin/1"
    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    archive.enqueue_listed_contents(
        db,
        user_id=user.id,
        contents=[
            ZhihuContent("专栏", "摘要", article_url, "article", 1),
            ZhihuContent("想法", "", pin_url, "pin", 2),
        ],
    )
    row = archive.get_by_source(db, user_id=user.id, source_url=article_url)
    assert row is not None
    assert row.status == ArticleStatus.PENDING
    assert archive.get_by_source(db, user_id=user.id, source_url=pin_url) is None


def test_browser_capture_saves_html_from_logged_in_page(db: Session) -> None:
    from verso_framework.providers.zhihu import ZhihuContent

    store = MemoryObjectStore()
    url = "https://zhuanlan.zhihu.com/p/14"
    archive = ArchiveService(store, key_prefix="articles")
    user = _user(db)
    archive.enqueue_listed_contents(
        db,
        user_id=user.id,
        contents=[ZhihuContent("待补", "", url, "article", 1)],
    )
    row = archive.capture_from_browser(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/14?utm=1",
        html="<h2>小节</h2><p>登录后看到的正文</p>",
        title="待补",
    )
    assert row.status == ArticleStatus.READY
    body = archive.get_markdown(db, user_id=user.id, source_url=url).decode()
    assert "登录后看到的正文" in body
    assert archive.list_failed_fetch(db, user_id=user.id) == []


def test_browser_capture_rejects_unknown_url(db: Session) -> None:
    from verso_common.exceptions import BizException

    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    with pytest.raises(BizException):
        archive.capture_from_browser(
            db,
            user_id=user.id,
            source_url="https://zhuanlan.zhihu.com/p/999",
            html="<p>x</p>",
        )


def test_list_queue_puts_failed_ahead_of_pending(db: Session) -> None:
    from verso_framework.providers.zhihu import ZhihuContent

    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    archive.enqueue_listed_contents(
        db,
        user_id=user.id,
        contents=[
            ZhihuContent("坏", "", "https://zhuanlan.zhihu.com/p/21", "article", 1),
            ZhihuContent("等", "", "https://zhuanlan.zhihu.com/p/22", "article", 1),
        ],
    )
    archive.mark_failed(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/21",
        content_type="article",
        title="坏",
        error_class="capture",
    )

    queue = archive.list_queue(db, user_id=user.id)
    assert [item.source_url for item in queue] == [
        "https://zhuanlan.zhihu.com/p/21",
        "https://zhuanlan.zhihu.com/p/22",
    ]
    assert archive.queue_counts(db, user_id=user.id) == (1, 1, 0)


def test_enqueue_listed_contents_does_not_fetch(db: Session) -> None:
    from verso_framework.providers.zhihu import ZhihuContent

    url = "https://www.zhihu.com/answer/1902358841586320975"
    archive = ArchiveService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    archive.enqueue_listed_contents(
        db,
        user_id=user.id,
        contents=[ZhihuContent("计算机也是坑", "", url, "answer", 1)],
    )
    row = archive.get_by_source(db, user_id=user.id, source_url=url)
    assert row is not None
    assert row.status == ArticleStatus.PENDING
    assert row.error_class is None
