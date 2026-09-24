"""知乎原文采集记录：登记标题、描述、状态和来源地址。"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from verso_app.server.collect.html import html_to_markdown
from verso_app.server.collect.keys import collection_object_key, content_sha256
from verso_app.server.collect.models import ArticleCollectionRecord
from verso_app.server.collect.urls import collectable_from_content, parse_collectable_url
from verso_common.enums import ArticleStatus, BizCode
from verso_common.exceptions import BizException
from verso_framework.config.storage import get_storage_settings
from verso_framework.providers.zhihu import ZhihuContent
from verso_framework.storage import ObjectStore, ObjectStoreError, get_object_store


class CollectService:
    """上传、读取、删除、查询已归档文章。正文由用户在知乎页回传。"""

    def __init__(
        self,
        store: ObjectStore | None = None,
        *,
        key_prefix: str | None = None,
    ) -> None:
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
    ) -> ArticleCollectionRecord:
        """覆盖上传 Markdown 并 upsert 采集记录。哈希未变且对象仍在则跳过上传。"""
        object_key = collection_object_key(user_id, source_url, prefix=self._key_prefix)
        digest = content_sha256(data)
        when = fetched_at or datetime.now(UTC)
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None:
            row = ArticleCollectionRecord(
                user_id=user_id,
                source_url=source_url,
                content_type=content_type,
                title=title,
                description=summary,
                object_key=object_key,
                status=ArticleStatus.PENDING,
            )
            db.add(row)
            db.flush()
        else:
            row.content_type = content_type
            row.title = title
            row.description = summary
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

    def enqueue_listed_contents(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        contents: Sequence[ZhihuContent],
    ) -> None:
        """登记知乎列表里的采集记录，不把正文写入知识库。"""
        for item in contents:
            target = collectable_from_content(url=item.url, content_type=item.content_type)
            if target is None:
                continue
            row = self.get_by_source(db, user_id=user_id, source_url=target.source_url)
            if row is None:
                row = self._row_for_target(db, user_id=user_id, target=target)
            if row is not None and row.status == ArticleStatus.READY:
                continue
            if row is None:
                db.add(
                    ArticleCollectionRecord(
                        user_id=user_id,
                        source_url=target.source_url,
                        content_type=target.kind,
                        title=item.title,
                        description=item.summary or None,
                        object_key=collection_object_key(
                            user_id, target.source_url, prefix=self._key_prefix
                        ),
                        status=ArticleStatus.PENDING,
                        error_class=None,
                    )
                )
            else:
                row.title = item.title or row.title
                row.description = item.summary or row.description
            db.flush()

    def discover_listed_contents(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        contents: Sequence[ZhihuContent],
    ) -> None:
        """首次打开采集页时登记待采集列表。已有记录则不再向知乎拉列表。"""
        if self.list_by_user(db, user_id=user_id):
            return
        self.enqueue_listed_contents(db, user_id=user_id, contents=contents)

    def mark_failed(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        source_url: str,
        content_type: str,
        title: str = "",
        summary: str | None = None,
        error_class: str,
    ) -> ArticleCollectionRecord:
        object_key = collection_object_key(user_id, source_url, prefix=self._key_prefix)
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None:
            row = ArticleCollectionRecord(
                user_id=user_id,
                source_url=source_url,
                content_type=content_type,
                title=title,
                description=summary,
                object_key=object_key,
                status=ArticleStatus.FAILED,
                error_class=error_class,
            )
            db.add(row)
        else:
            row.content_type = content_type
            row.title = title
            row.description = summary
            row.object_key = object_key
            row.status = ArticleStatus.FAILED
            row.error_class = error_class
        db.flush()
        return row

    def get_markdown(self, db: Session, *, user_id: uuid.UUID, source_url: str) -> bytes:
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None or row.status != ArticleStatus.READY:
            raise KeyError(source_url)
        return self._store.get(row.object_key)

    def get_by_source(
        self, db: Session, *, user_id: uuid.UUID, source_url: str
    ) -> ArticleCollectionRecord | None:
        return db.scalar(
            select(ArticleCollectionRecord).where(
                ArticleCollectionRecord.user_id == user_id,
                ArticleCollectionRecord.source_url == source_url,
            )
        )

    def _row_for_target(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        target,
    ) -> ArticleCollectionRecord | None:
        for row in self.list_by_user(db, user_id=user_id):
            parsed = parse_collectable_url(row.source_url)
            if (
                parsed is not None
                and parsed.kind == target.kind
                and parsed.content_id == target.content_id
            ):
                return row
        return None

    def list_by_user(self, db: Session, *, user_id: uuid.UUID) -> list[ArticleCollectionRecord]:
        return list(
            db.scalars(
                select(ArticleCollectionRecord)
                .where(ArticleCollectionRecord.user_id == user_id)
                .order_by(ArticleCollectionRecord.created_at.asc())
            ).all()
        )

    def list_failed_fetch(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
    ) -> list[ArticleCollectionRecord]:
        return list(
            sorted(
                (
                    row
                    for row in self.list_by_user(db, user_id=user_id)
                    if row.status == ArticleStatus.FAILED and row.error_class == "fetch"
                ),
                key=lambda row: row.updated_at,
            )
        )

    def list_queue(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
    ) -> list[ArticleCollectionRecord]:
        """工作台待办：pending 与 failed，失败排前面。"""
        rows = [
            row
            for row in self.list_by_user(db, user_id=user_id)
            if row.status != ArticleStatus.READY
        ]
        rows.sort(
            key=lambda row: (
                0 if row.status == ArticleStatus.FAILED else 1,
                row.updated_at or row.created_at,
            )
        )
        return rows

    def queue_counts(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
    ) -> tuple[int, int, int]:
        pending = 0
        failed = 0
        ready = 0
        for row in self.list_by_user(db, user_id=user_id):
            if row.status == ArticleStatus.READY:
                ready += 1
            elif row.status == ArticleStatus.FAILED:
                failed += 1
            else:
                pending += 1
        return pending, failed, ready

    def capture_from_browser(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        source_url: str,
        html: str,
        title: str = "",
    ) -> ArticleCollectionRecord:
        """用户在已登录的知乎页里抓到 HTML，发回本站。不接收知乎 Cookie。"""
        target = parse_collectable_url(source_url)
        if target is None:
            raise BizException("只接收专栏或单条回答链接", code=BizCode.BAD_REQUEST)
        row = self._row_for_target(db, user_id=user_id, target=target)
        if row is None:
            raise BizException("不是待补抓的文章", code=BizCode.NOT_FOUND)
        markdown = html_to_markdown(html)
        if not markdown:
            raise BizException("页面里没有正文", code=BizCode.BAD_REQUEST)
        return self.put_markdown(
            db,
            user_id=user_id,
            source_url=row.source_url,
            data=markdown.encode("utf-8"),
            content_type=row.content_type or target.kind,
            title=title or row.title,
            summary=row.description,
        )

    def delete(self, db: Session, *, user_id: uuid.UUID, source_url: str) -> bool:
        row = self.get_by_source(db, user_id=user_id, source_url=source_url)
        if row is None:
            return False
        self._store.delete(row.object_key)
        db.delete(row)
        db.flush()
        return True
