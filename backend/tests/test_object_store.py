from unittest.mock import MagicMock, patch

import httpx
import pytest

from verso_framework.config.storage import StorageSettings
from verso_framework.storage import (
    KodoObjectStore,
    MemoryObjectStore,
    ObjectStoreError,
    build_object_store,
)


class _Info:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def __str__(self) -> str:
        return f"status={self.status_code}"


def test_memory_put_get_delete_list() -> None:
    store = MemoryObjectStore()
    stored = store.put("articles/u/a.md", b"# hi", content_type="text/markdown")
    assert stored.size == 4
    assert store.exists("articles/u/a.md")
    assert store.get("articles/u/a.md") == b"# hi"
    assert store.list_keys("articles/") == ["articles/u/a.md"]
    assert store.delete("articles/u/a.md") is True
    assert store.exists("articles/u/a.md") is False
    assert store.delete("articles/u/a.md") is False
    with pytest.raises(KeyError):
        store.get("articles/u/a.md")


def test_build_object_store_requires_kodo_credentials() -> None:
    with pytest.raises(ObjectStoreError):
        build_object_store(StorageSettings())


@patch("verso_framework.storage.kodo.put_data")
@patch("verso_framework.storage.kodo.BucketManager")
@patch("verso_framework.storage.kodo.Auth")
def test_kodo_put_delete_exists_list(
    auth_cls: MagicMock, bucket_cls: MagicMock, put_data: MagicMock
) -> None:
    auth = auth_cls.return_value
    auth.upload_token.return_value = "token"
    auth.private_download_url.side_effect = lambda url, expires: f"{url}?e={expires}"
    bucket = bucket_cls.return_value
    put_data.return_value = ({"hash": "etag-1"}, _Info(200))
    bucket.delete.return_value = ({}, _Info(200))
    bucket.stat.side_effect = [
        ({"hash": "etag-1"}, _Info(200)),
        (None, _Info(612)),
    ]
    bucket.list.return_value = (
        {"items": [{"key": "articles/u/a.md"}]},
        True,
        _Info(200),
    )

    store = KodoObjectStore(
        access_key="ak",
        secret_key="sk",
        bucket="verso",
        domain="cdn.example.com",
    )
    stored = store.put("articles/u/a.md", b"# hi")
    assert stored.etag == "etag-1"
    put_data.assert_called_once()
    assert store.exists("articles/u/a.md") is True
    assert store.list_keys("articles/") == ["articles/u/a.md"]
    assert store.delete("articles/u/a.md") is True
    assert store.exists("missing.md") is False

    with patch("verso_framework.storage.kodo.httpx.get") as get:
        get.return_value = httpx.Response(200, content=b"# hi")
        assert store.get("articles/u/a.md") == b"# hi"
        get.assert_called_once()
        called_url = get.call_args.args[0]
        assert called_url.startswith("https://cdn.example.com/articles/u/a.md")
