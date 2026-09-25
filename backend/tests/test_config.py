import os

import pytest
from pydantic import ValidationError

from verso_framework.config.database import DatabaseSettings
from verso_framework.config.milvus import MilvusSettings
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


def test_milvus_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("MILVUS_"):
            monkeypatch.delenv(key, raising=False)
    settings = MilvusSettings(_env_file=None)
    assert settings.uri == "http://localhost:19530"
    assert settings.token == ""
    assert settings.db == "default"
    assert settings.collection == "verso_chunks"
    assert settings.timeout_sec == 10
    assert settings.num_partitions == 64
