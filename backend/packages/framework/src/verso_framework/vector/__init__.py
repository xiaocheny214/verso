"""Milvus 客户端。import 不连库；首次 ``get_milvus_client()`` 才建连。

后续 retrieve 这样用，本模块不负责切块、schema 或过滤表达式::

    client = get_milvus_client()
    collection = get_milvus_settings().collection
    client.search(
        collection_name=collection,
        data=[vector],
        filter=expr,
        limit=top_k,
        output_fields=["article_id", "chunk_index", "text"],
    )
"""

from __future__ import annotations

from functools import lru_cache

from pymilvus import MilvusClient

from verso_framework.config.milvus import MilvusSettings, get_milvus_settings


def build_milvus_client(settings: MilvusSettings | None = None) -> MilvusClient:
    """用给定配置构造客户端。空 token 不传给 pymilvus。"""
    cfg = settings if settings is not None else get_milvus_settings()
    kwargs: dict[str, object] = {
        "uri": cfg.uri,
        "db_name": cfg.db,
        "timeout": cfg.timeout_sec,
    }
    if cfg.token:
        kwargs["token"] = cfg.token
    return MilvusClient(**kwargs)


@lru_cache
def get_milvus_client() -> MilvusClient:
    return build_milvus_client()


__all__ = ["build_milvus_client", "get_milvus_client"]
