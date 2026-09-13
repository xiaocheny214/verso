import httpx
import pytest

from verso_framework.config.app import AppSettings
from verso_framework.providers.zhihu.user_data import HttpxUserDataClient, ZhihuUserDataError

_SETTINGS = AppSettings(
    zhihu_client_id="app-id",
    zhihu_client_secret="app-key",
    zhihu_access_secret="platform-secret",
    zhihu_redirect_uri="http://localhost:8000/auth/zhihu/callback",
)


def _client(monkeypatch, handler) -> HttpxUserDataClient:
    client = HttpxUserDataClient(_SETTINGS)
    monkeypatch.setattr(
        client, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return client


def test_list_contents_success_empty_items(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20000, "Data": {"Items": []}})

    assert _client(monkeypatch, handler).list_contents("tok") == []


def test_list_contents_http_error_is_not_empty(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": 20000, "Data": {"Items": []}})

    with pytest.raises(ZhihuUserDataError, match="HTTP 500"):
        _client(monkeypatch, handler).list_contents("tok")


def test_list_contents_biz_error_is_not_empty(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40001, "message": "fail", "Data": {"Items": []}})

    with pytest.raises(ZhihuUserDataError, match="code=40001"):
        _client(monkeypatch, handler).list_contents("tok")


def test_list_contents_network_error_is_not_empty(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    with pytest.raises(ZhihuUserDataError, match="network error"):
        _client(monkeypatch, handler).list_contents("tok")
