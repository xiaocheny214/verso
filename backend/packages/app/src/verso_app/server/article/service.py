"""授权用户文章归档：正文进对象存储，元数据进 Postgres。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_app.server.article.keys import article_object_key, content_sha256
from verso_app.server.article.models import UserArticle
from verso_common.enums import ArticleStatus
from verso_framework.config.storage import get_storage_settings
from verso_framework.storage import ObjectStore, ObjectStoreError, get_object_store


class ArchiveService:
    """上传、读取、删除、查询已归档文章。不抓网页。"""

    def __init__(self, store: ObjectStore | None = None, *, key_prefix: str | None = None) -> None:
        self._store = store if store is not None else get_object_store()
        self._key_prefix = (
            key_prefix if key_prefix is not None else get_storage_settings().key_prefix
        )

    def put_markdown(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        source_url: str,
        data: bytes,
        content_type: str,
        title: str = "",
        summary: str | None = None,
        fetched_at: datetime | None = None,
    ) -> UserArticle:
        """覆盖上传 Markdown 并 upsert 元数据。哈希未变且对象仍在则跳过上传。"""
        object_key = article_object_key(user_id, source_url, prefix=self._key_prefix)
        digest = content_sha256(data)
        when = fetched_at or datetime.now(UTC)
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None:
            row = UserArticle(
                user_id=user_id,
                source_url=source_url,
                content_type=content_type,
                title=title,
                summary=summary,
                object_key=object_key,
                status=ArticleStatus.PENDING,
            )
            db.add(row)
            db.flush()
        else:
            row.content_type = content_type
            row.title = title
            row.summary = summary
            row.object_key = object_key

        if (
            row.status == ArticleStatus.READY
            and row.content_hash == digest
            and self._store.exists(object_key)
        ):
            return row

        try:
            stored = self._store.put(object_key, data, content_type="text/markdown; charset=utf-8")
        except ObjectStoreError:
            row.status = ArticleStatus.FAILED
            row.error_class = "object_store_put"
            db.flush()
            raise

        row.content_hash = digest
        row.byte_size = stored.size
        row.status = ArticleStatus.READY
        row.error_class = None
        row.fetched_at = when
        db.flush()
        return row

    def get_markdown(self, db: Session, *, user_id: uuid.UUID, source_url: str) -> bytes:
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None or row.status != ArticleStatus.READY:
            raise KeyError(source_url)
        return self._store.get(row.object_key)

    def get_by_source(
        self, db: Session, *, user_id: uuid.UUID, source_url: str
    ) -> UserArticle | None:
        return db.scalar(
            select(UserArticle).where(
                UserArticle.user_id == user_id,
                UserArticle.source_url == source_url,
            )
        )

    def list_by_user(self, db: Session, *, user_id: uuid.UUID) -> list[UserArticle]:
        return list(
            db.scalars(
                select(UserArticle)
                .where(UserArticle.user_id == user_id)
                .order_by(UserArticle.created_at.asc())
            ).all()
        )

    def delete(self, db: Session, *, user_id: uuid.UUID, source_url: str) -> bool:
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None:
            return False
        self._store.delete(row.object_key)
        db.delete(row)
        db.flush()
        return True
