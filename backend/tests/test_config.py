import pytest
from pydantic import ValidationError
from verso_framework.config.database import DatabaseSettings
from verso_framework.config.redis import RedisSettings


def test_database_url_escapes_password() -> None:
    settings = DatabaseSettings(
        host="localhost",
        port=5432,
        user="verso",
        password="verso:dev@x",
        db="verso",
    )
    assert settings.url == "postgresql+psycopg://verso:verso%3Adev%40x@localhost:5432/verso"


def test_database_password_must_be_long_enough() -> None:
    with pytest.raises(ValidationError):
        DatabaseSettings(password="short")


def test_redis_default_url() -> None:
    assert RedisSettings().url == "redis://localhost:6379/0"
