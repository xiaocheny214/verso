"""按配置构造对象存储。生产为七牛云 Kodo。"""

from __future__ import annotations

from functools import lru_cache

from verso_framework.config.storage import StorageSettings, get_storage_settings
from verso_framework.storage.kodo import KodoObjectStore
from verso_framework.storage.ports import ObjectStore


def build_object_store(settings: StorageSettings | None = None) -> ObjectStore:
    """用当前配置构造 Kodo 客户端。缺凭证时在初始化阶段失败。"""
    cfg = settings or get_storage_settings()
    return KodoObjectStore(
        access_key=cfg.access_key,
        secret_key=cfg.secret_key,
        bucket=cfg.bucket,
        domain=cfg.domain,
        private=cfg.private,
        url_expires_sec=cfg.url_expires_sec,
    )


@lru_cache
def get_object_store() -> ObjectStore:
    return build_object_store()
