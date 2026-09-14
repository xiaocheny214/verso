"""进程级应用配置：Cookie Session、知乎 OAuth、成色阈值、质量路径用的模型。

密钥不进仓库。字段前缀 ``VERSO_``。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from verso_common.constants import (
    REPUTATION_GOOD_DELTA,
    REPUTATION_INITIAL_SCORE,
    REPUTATION_MIN_ACTIVE_SCORE,
    REPUTATION_POOR_DELTA,
    REPUTATION_SCORE_MAX,
)


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
    llm_base_url: str = ""
    llm_model: str = ""
    reputation_score_max: int = REPUTATION_SCORE_MAX
    reputation_initial_score: int = REPUTATION_INITIAL_SCORE
    reputation_poor_delta: int = REPUTATION_POOR_DELTA
    reputation_good_delta: int = REPUTATION_GOOD_DELTA
    reputation_min_active_score: int = REPUTATION_MIN_ACTIVE_SCORE


@lru_cache
def get_app_settings() -> AppSettings:
    return AppSettings()
