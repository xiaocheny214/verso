"""进程级应用配置：Cookie Session、知乎 OAuth、质量路径用的模型。

密钥不进仓库。字段前缀 ``VERSO_``。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VERSO_",
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    session_cookie: str = "verso_session"
    session_ttl_sec: int = 7 * 24 * 3600
    oauth_intent_ttl_sec: int = 600
    zhihu_client_id: str = ""
    zhihu_client_secret: str = ""
    zhihu_redirect_uri: str = "http://localhost:8000/auth/zhihu/callback"
    zhihu_access_secret: str = ""
    public_origin: str = "http://localhost:3000"
    create_tables: bool = False
    llm_api_key: str = ""
    llm_model: str = ""


@lru_cache
def get_app_settings() -> AppSettings:
    return AppSettings()
