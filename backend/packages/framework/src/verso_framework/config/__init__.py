from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WENJU_", extra="ignore")

    database_url: str = "postgresql+psycopg://verso:verso@localhost:5432/verso"
    redis_url: str = "redis://localhost:6379/0"
    session_cookie: str = "verso_session"
    zhihu_client_id: str = ""
    zhihu_client_secret: str = ""
    llm_api_key: str = ""
    llm_model: str = ""


def get_settings() -> Settings:
    return Settings()
