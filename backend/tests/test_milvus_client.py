from unittest.mock import MagicMock, patch

from verso_framework.config.milvus import MilvusSettings
from verso_framework.vector import build_milvus_client, get_milvus_client


def _settings(**overrides: object) -> MilvusSettings:
    base = {
        "uri": "http://milvus:19530",
        "token": "",
        "db": "default",
        "collection": "verso_chunks",
        "timeout_sec": 10,
    }
    base.update(overrides)
    return MilvusSettings(**base)


@patch("verso_framework.vector.MilvusClient")
def test_build_omits_empty_token(client_cls: MagicMock) -> None:
    build_milvus_client(_settings())
    client_cls.assert_called_once_with(
        uri="http://milvus:19530",
        db_name="default",
        timeout=10,
    )


@patch("verso_framework.vector.MilvusClient")
def test_build_passes_token(client_cls: MagicMock) -> None:
    build_milvus_client(_settings(token="root:secret"))
    assert client_cls.call_args.kwargs["token"] == "root:secret"


@patch("verso_framework.vector.MilvusClient")
def test_get_client_is_cached(client_cls: MagicMock) -> None:
    get_milvus_client.cache_clear()
    client_cls.return_value = MagicMock()
    try:
        assert get_milvus_client() is get_milvus_client()
        client_cls.assert_called_once()
    finally:
        get_milvus_client.cache_clear()
