"""查询术语归一化核心服务。

管理租户隔离的术语映射规则（CRUD），支持 Redis 缓存、防击穿/防穿透空标记机制，
并在检索前按 priority DESC, length(source_term) DESC 进行长词优先替换。
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from verso_app.server.term_mapping.models import QueryTermMapping
from verso_common.enums import BizCode
from verso_common.exceptions import BizException

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger("verso.term_mapping")

CACHE_KEY_PREFIX = "verso:term_mappings:"
CACHE_TTL_SECONDS = 3600
EMPTY_CACHE_SENTINEL = "__empty__"
_UNSET = object()


class QueryTermMappingService:
    """查询术语映射服务。"""

    def __init__(self, session: Session, redis: Redis | None = None) -> None:
        self._session = session
        self._redis = redis

    def _cache_key(self, user_id: uuid.UUID) -> str:
        return f"{CACHE_KEY_PREFIX}{user_id}"

    def _invalidate_cache(self, user_id: uuid.UUID) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(self._cache_key(user_id))
            except Exception as exc:
                logger.warning("删除 Redis 术语映射缓存失败 user_id=%s: %s", user_id, exc)

    def _validate_source_term(self, source_term: str) -> str:
        clean = source_term.strip()
        if not clean:
            raise BizException("原词 source_term 不能为空", code=BizCode.BAD_REQUEST)
        if len(clean) > 128:
            raise BizException("原词 source_term 长度不能超过 128", code=BizCode.BAD_REQUEST)
        return clean

    def _validate_target_term(self, target_term: str) -> str:
        clean = target_term.strip()
        if not clean:
            raise BizException("目标词 target_term 不能为空", code=BizCode.BAD_REQUEST)
        if len(clean) > 128:
            raise BizException("目标词 target_term 长度不能超过 128", code=BizCode.BAD_REQUEST)
        return clean

    def _check_source_term_unique(
        self,
        *,
        user_id: uuid.UUID,
        source_term: str,
        exclude_id: uuid.UUID | None = None,
    ) -> None:
        query = select(QueryTermMapping.id).where(
            QueryTermMapping.user_id == user_id,
            QueryTermMapping.source_term == source_term,
        )
        if exclude_id is not None:
            query = query.where(QueryTermMapping.id != exclude_id)
        if self._session.scalar(query) is not None:
            raise BizException("该原词映射规则已存在", code=BizCode.CONFLICT)

    def create(
        self,
        *,
        user_id: uuid.UUID,
        source_term: str,
        target_term: str,
        match_type: int = 1,
        priority: int = 0,
        enabled: bool = True,
        remark: str | None = None,
    ) -> QueryTermMapping:
        clean_source = self._validate_source_term(source_term)
        clean_target = self._validate_target_term(target_term)
        self._check_source_term_unique(user_id=user_id, source_term=clean_source)

        row = QueryTermMapping(
            user_id=user_id,
            source_term=clean_source,
            target_term=clean_target,
            match_type=match_type,
            priority=priority,
            enabled=enabled,
            remark=remark.strip() if remark is not None and remark.strip() else None,
        )
        self._session.add(row)
        self._session.flush()
        self._invalidate_cache(user_id)
        return row

    def get(self, *, user_id: uuid.UUID, mapping_id: uuid.UUID) -> QueryTermMapping:
        row = self._session.scalar(
            select(QueryTermMapping).where(
                QueryTermMapping.id == mapping_id,
                QueryTermMapping.user_id == user_id,
            )
        )
        if row is None:
            raise BizException("术语映射规则不存在", code=BizCode.NOT_FOUND)
        return row

    def update(
        self,
        *,
        user_id: uuid.UUID,
        mapping_id: uuid.UUID,
        source_term: str | None = None,
        target_term: str | None = None,
        match_type: int | None = None,
        priority: int | None = None,
        enabled: bool | None = None,
        remark: object = _UNSET,
    ) -> QueryTermMapping:
        row = self.get(user_id=user_id, mapping_id=mapping_id)

        if source_term is not None:
            clean_source = self._validate_source_term(source_term)
            self._check_source_term_unique(
                user_id=user_id, source_term=clean_source, exclude_id=row.id
            )
            row.source_term = clean_source

        if target_term is not None:
            row.target_term = self._validate_target_term(target_term)

        if match_type is not None:
            row.match_type = match_type

        if priority is not None:
            row.priority = priority

        if enabled is not None:
            row.enabled = enabled

        if remark is not _UNSET:
            row.remark = remark.strip() if isinstance(remark, str) and remark.strip() else None

        self._session.flush()
        self._invalidate_cache(user_id)
        return row

    def delete(self, *, user_id: uuid.UUID, mapping_id: uuid.UUID) -> None:
        row = self.get(user_id=user_id, mapping_id=mapping_id)
        self._session.delete(row)
        self._session.flush()
        self._invalidate_cache(user_id)

    def list_mappings(
        self,
        *,
        user_id: uuid.UUID,
        keyword: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[QueryTermMapping], int]:
        """按租户查询术语映射列表，支持分页和 keyword 过滤。

        返回 (items, total)。
        """
        stmt = select(QueryTermMapping).where(QueryTermMapping.user_id == user_id)
        count_stmt = (
            select(func.count())
            .select_from(QueryTermMapping)
            .where(QueryTermMapping.user_id == user_id)
        )

        if enabled is not None:
            stmt = stmt.where(QueryTermMapping.enabled == enabled)
            count_stmt = count_stmt.where(QueryTermMapping.enabled == enabled)

        if keyword:
            kw = f"%{keyword.strip()}%"
            cond = (
                QueryTermMapping.source_term.ilike(kw)
                | QueryTermMapping.target_term.ilike(kw)
                | QueryTermMapping.remark.ilike(kw)
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = self._session.scalar(count_stmt) or 0

        stmt = stmt.order_by(
            QueryTermMapping.priority.desc(),
            func.length(QueryTermMapping.source_term).desc(),
            QueryTermMapping.id.asc(),
        )

        if page_size > 0:
            offset = max(0, (page - 1) * page_size)
            stmt = stmt.offset(offset).limit(page_size)

        items = list(self._session.scalars(stmt).all())
        return items, total

    def load_mappings(self, user_id: uuid.UUID) -> list[dict[str, str]]:
        """加载当前用户生效的术语映射列表（按 priority DESC, length DESC 排序）。

        返回格式例如：`[{"source_term": "向量库", "target_term": "向量数据库"}, ...]`
        具有 Redis 缓存支持及空标记防缓存击穿/穿透。
        """
        key = self._cache_key(user_id)
        if self._redis is not None:
            try:
                cached = self._redis.get(key)
                if cached is not None:
                    data = json.loads(cached)
                    if isinstance(data, dict) and data.get(EMPTY_CACHE_SENTINEL):
                        return []
                    if isinstance(data, list):
                        return data
            except Exception as exc:
                logger.warning("读取 Redis 术语映射缓存失败 user_id=%s: %s", user_id, exc)

        # 查 DB：仅加载 enabled=True 的规则
        stmt = (
            select(QueryTermMapping.source_term, QueryTermMapping.target_term)
            .where(
                QueryTermMapping.user_id == user_id,
                QueryTermMapping.enabled.is_(True),
            )
            .order_by(
                QueryTermMapping.priority.desc(),
                func.length(QueryTermMapping.source_term).desc(),
                QueryTermMapping.id.asc(),
            )
        )
        rows = self._session.execute(stmt).all()
        result = [{"source_term": row.source_term, "target_term": row.target_term} for row in rows]

        if self._redis is not None:
            try:
                if not result:
                    self._redis.set(
                        key,
                        json.dumps({EMPTY_CACHE_SENTINEL: True}),
                        ex=CACHE_TTL_SECONDS,
                    )
                else:
                    self._redis.set(
                        key,
                        json.dumps(result),
                        ex=CACHE_TTL_SECONDS,
                    )
            except Exception as exc:
                logger.warning("写入 Redis 术语映射缓存失败 user_id=%s: %s", user_id, exc)

        return result

    def normalize(self, text: str, *, user_id: uuid.UUID) -> str:
        """对 text 顺序应用该用户的术语映射替换。

        由于 load_mappings 已保证长词优先（按 priority DESC + length DESC），
        能正确避免子串误替换，如“向量数据库”先于“向量”被替换。
        """
        if not text:
            return text

        mappings = self.load_mappings(user_id)
        normalized = text
        for item in mappings:
            src = item.get("source_term", "")
            tgt = item.get("target_term", "")
            if src and src in normalized:
                normalized = normalized.replace(src, tgt)

        return normalized
