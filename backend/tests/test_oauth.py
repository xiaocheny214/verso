from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from verso_framework.config.app import AppSettings
from verso_framework.providers.zhihu.oauth import HttpxOAuthClient

_SETTINGS = AppSettings(
    zhihu_client_id="app-id",
    zhihu_client_secret="app-key",
    zhihu_access_secret="platform-secret",
    zhihu_redirect_uri="http://localhost:8000/auth/zhihu/callback",
)


def _client(monkeypatch, handler) -> HttpxOAuthClient:
    client = HttpxOAuthClient(_SETTINGS)
    monkeypatch.setattr(
        client, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    return client


def test_authorize_url_matches_hackathon_spec() -> None:
    url = HttpxOAuthClient(_SETTINGS).authorization_url("nonce-1")
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "openapi.zhihu.com"
    assert parsed.path == "/authorize"
    assert query["app_id"] == ["app-id"]
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["http://localhost:8000/auth/zhihu/callback"]
    assert query["state"] == ["nonce-1"]


def test_exchange_code_reads_wrapped_access_token(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        assert request.url.path == "/access_token"
        assert body["grant_type"] == "authorization_code"
        assert body["code"] == "from-callback"
        assert body["app_id"] == "app-id"
        assert body["app_key"] == "app-key"
        assert "authorization_code" not in body
        return httpx.Response(
            200,
            json={"code": 20000, "Data": {"access_token": "user-tok", "expires_in": 7200}},
        )

    token = _client(monkeypatch, handler).exchange_code("from-callback")
    assert token.access_token == "user-tok"
    assert token.expires_in == 7200


def test_fetch_profile_uses_user_data_headers(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["Authorization"]
        seen["oauth"] = request.headers["X-OAuth-Token"]
        seen["ts"] = request.headers["X-Request-Timestamp"]
        return httpx.Response(
            200,
            json={
                "code": 20000,
                "Data": {
                    "UrlToken": "alice",
                    "Fullname": "Alice",
                    "AvatarUrl": "https://x/a.png",
                    "Headline": "dev",
                },
            },
        )

    profile = _client(monkeypatch, handler).fetch_profile("user-tok")
    assert profile.url_token == "alice"
    assert profile.name == "Alice"
    assert seen["authorization"] == "Bearer platform-secret"
    assert seen["oauth"] == "user-tok"
    assert seen["ts"].isdigit()


def test_fetch_profile_accepts_uppercase_success_and_nested_user(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"Code": 0, "Data": {"User": {"urlToken": "alice", "Name": "Alice"}}},
        )

    profile = _client(monkeypatch, handler).fetch_profile("user-tok")
    assert profile.url_token == "alice"
    assert profile.name == "Alice"


def test_fetch_profile_accepts_numeric_url_token(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20000, "Data": {"UrlToken": 12345}})

    assert _client(monkeypatch, handler).fetch_profile("user-tok").url_token == "12345"


def test_fetch_profile_http_error_is_not_missing_token(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"code": 20001, "Message": "not found"})

    with pytest.raises(RuntimeError, match="zhihu profile HTTP 404"):
        _client(monkeypatch, handler).fetch_profile("user-tok")


def test_fetch_profile_biz_error_is_not_missing_token(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 20001, "Message": "鉴权失败", "Data": {}},
        )

    with pytest.raises(RuntimeError, match="zhihu profile code=20001"):
        _client(monkeypatch, handler).fetch_profile("user-tok")


def test_fetch_profile_open_id_without_url_token_still_fails(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20000, "Data": {"OpenId": "x"}})

    with pytest.raises(RuntimeError, match="zhihu profile missing url_token keys="):
        _client(monkeypatch, handler).fetch_profile("user-tok")
