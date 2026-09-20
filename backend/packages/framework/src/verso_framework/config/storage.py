"""七牛云 Kodo 对象存储配置。

字段前缀 ``OBJECT_STORAGE_``。密钥不进仓库。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageSettings(BaseSettings):
    """Kodo 空间与访问凭证。"""

    model_config = SettingsConfigDict(
        env_prefix="OBJECT_STORAGE_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    access_key: str = ""
    secret_key: str = ""
    bucket: str = ""
    domain: str = ""
    private: bool = True
    url_expires_sec: int = 3600
    key_prefix: str = "articles"


@lru_cache
def get_storage_settings() -> StorageSettings:
    return StorageSettings()
