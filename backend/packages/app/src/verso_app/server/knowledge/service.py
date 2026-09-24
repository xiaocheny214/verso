"""知识库 CRUD、租户隔离和旧文章归属回填。"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from verso_app.server.article.models import UserArticle
from verso_app.server.knowledge.models import KnowledgeBase
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_framework.config import get_app_settings

_COLLECTION_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")


class KnowledgeService:
    """当前用户拥有的知识库。所有按 id 的查询都带 user_id。"""

    def create(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        name: str,
        collection_name: str | None = None,
        storage_profile_id: uuid.UUID | None = None,
    ) -> KnowledgeBase:
        clean_name = name.strip()
        if not clean_name:
            raise BizException("知识库名称不能为空", code=BizCode.BAD_REQUEST)
        if self._find_by_name(db, user_id=user_id, name=clean_name) is not None:
            raise BizException("知识库名称已存在", code=BizCode.CONFLICT)
        row_id = uuid.uuid4()
        row = KnowledgeBase(
            id=row_id,
            user_id=user_id,
            name=clean_name,
            embedding_model=get_app_settings().llm_embedding_model,
            collection_name=self._resolve_collection_name(
                db,
                user_id=user_id,
                name=clean_name,
                row_id=row_id,
                collection_name=collection_name,
            ),
            storage_profile_id=storage_profile_id,
        )
        db.add(row)
        db.flush()
        return row

    def list(self, db: Session, *, user_id: uuid.UUID) -> list[KnowledgeBase]:
        return list(
            db.scalars(
                select(KnowledgeBase)
                .where(KnowledgeBase.user_id == user_id)
                .order_by(KnowledgeBase.created_at.asc(), KnowledgeBase.id.asc())
            ).all()
        )

    def get(
        self, db: Session, *, user_id: uuid.UUID, knowledge_base_id: uuid.UUID
    ) -> KnowledgeBase:
        row = db.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.user_id == user_id,
            )
        )
        if row is None:
            raise BizException("知识库不存在", code=BizCode.NOT_FOUND)
        return row

    def update(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        knowledge_base_id: uuid.UUID,
        name: str | None = None,
        collection_name: str | None = None,
        storage_profile_id: uuid.UUID | None = None,
        update_storage_profile: bool = False,
    ) -> KnowledgeBase:
        row = self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        if name is not None:
            clean_name = name.strip()
            if not clean_name:
                raise BizException("知识库名称不能为空", code=BizCode.BAD_REQUEST)
            duplicate = self._find_by_name(db, user_id=user_id, name=clean_name, exclude_id=row.id)
            if duplicate is not None:
                raise BizException("知识库名称已存在", code=BizCode.CONFLICT)
            row.name = clean_name
        if collection_name is not None:
            row.collection_name = self._require_collection_name(
                db,
                user_id=user_id,
                collection_name=collection_name,
                exclude_id=row.id,
            )
        if update_storage_profile:
            row.storage_profile_id = storage_profile_id
        db.flush()
        return row

    def delete(self, db: Session, *, user_id: uuid.UUID, knowledge_base_id: uuid.UUID) -> None:
        row = self.get(db, user_id=user_id, knowledge_base_id=knowledge_base_id)
        if db.scalar(select(exists().where(UserArticle.knowledge_base_id == row.id))):
            raise BizException("知识库仍包含文章，不能删除", code=BizCode.CONFLICT)
        db.delete(row)
        db.flush()

    def get_or_create_default(self, db: Session, *, user_id: uuid.UUID) -> KnowledgeBase:
        row = self._find_by_name(db, user_id=user_id, name="Default")
        if row is not None:
            return row
        return self.create(db, user_id=user_id, name="Default")

    def backfill_default_knowledge_bases(self, db: Session) -> None:
        """为已有文章的用户创建 Default，并把孤立文章挂上去。"""
        user_ids = list(
            db.scalars(
                select(UserArticle.user_id)
                .where(UserArticle.knowledge_base_id.is_(None))
                .distinct()
            )
        )
        for user_id in user_ids:
            base = self.get_or_create_default(db, user_id=user_id)
            db.query(UserArticle).filter(
                UserArticle.user_id == user_id,
                UserArticle.knowledge_base_id.is_(None),
            ).update({"knowledge_base_id": base.id}, synchronize_session=False)
        db.flush()

    def _resolve_collection_name(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        name: str,
        row_id: uuid.UUID,
        collection_name: str | None,
    ) -> str:
        if collection_name is not None:
            return self._require_collection_name(
                db, user_id=user_id, collection_name=collection_name
            )
        candidate = _derived_collection_name(name, row_id)
        if self._find_by_collection_name(db, user_id=user_id, collection_name=candidate) is None:
            return candidate
        fallback = f"kb_{row_id.hex}"
        if self._find_by_collection_name(db, user_id=user_id, collection_name=fallback) is not None:
            raise BizException("collection_name 已存在", code=BizCode.CONFLICT)
        return fallback

    def _require_collection_name(
        self,
        db: Session,
        *,
        user_id: uuid.UUID,
        collection_name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> str:
        clean = collection_name.strip().lower()
        if not _COLLECTION_NAME_RE.fullmatch(clean):
            raise BizException(
                "collection_name 只能包含小写字母、数字和下划线，并以字母开头",
                code=BizCode.BAD_REQUEST,
            )
        duplicate = self._find_by_collection_name(
            db, user_id=user_id, collection_name=clean, exclude_id=exclude_id
        )
        if duplicate is not None:
            raise BizException("collection_name 已存在", code=BizCode.CONFLICT)
        return clean

    @staticmethod
    def _find_by_name(
        db: Session,
        *,
        user_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBase.id != exclude_id)
        return db.scalar(stmt)

    @staticmethod
    def _find_by_collection_name(
        db: Session,
        *,
        user_id: uuid.UUID,
        collection_name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> KnowledgeBase | None:
        stmt = select(KnowledgeBase).where(
            KnowledgeBase.user_id == user_id,
            KnowledgeBase.collection_name == collection_name,
        )
        if exclude_id is not None:
            stmt = stmt.where(KnowledgeBase.id != exclude_id)
        return db.scalar(stmt)


def _derived_collection_name(name: str, row_id: uuid.UUID) -> str:
    if name == "Default":
        return "default"
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)
    if _COLLECTION_NAME_RE.fullmatch(slug):
        return slug
    return f"kb_{row_id.hex}"
