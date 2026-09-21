"""Milvus 连接配置。

字段前缀 ``MILVUS_``。默认对齐仓库根 ``docker-compose.yml`` 的 standalone。
import 本模块不连库；真正建连在 ``verso_framework.vector``。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class MilvusSettings(BaseSettings):
    """Milvus 地址、库名和默认 collection。"""

    model_config = SettingsConfigDict(
        env_prefix="MILVUS_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    uri: str = "http://localhost:19530"
    token: str = ""
    db: str = "default"
    collection: str = "verso_chunks"
    timeout_sec: float = 10


@lru_cache
def get_milvus_settings() -> MilvusSettings:
    return MilvusSettings()
