from urllib.parse import parse_qs, urlparse

import httpx

from verso_framework.config.app import AppSettings
from verso_framework.providers.zhihu.oauth import HttpxOAuthClient

_SETTINGS = AppSettings(
    zhihu_client_id="app-id",
    zhihu_client_secret="app-key",
    zhihu_access_secret="platform-secret",
    zhihu_redirect_uri="http://localhost:8000/auth/zhihu/callback",
)


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
    client = HttpxOAuthClient(_SETTINGS)

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

    monkeypatch.setattr(
        client, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    token = client.exchange_code("from-callback")
    assert token.access_token == "user-tok"
    assert token.expires_in == 7200


def test_fetch_profile_uses_user_data_headers(monkeypatch) -> None:
    client = HttpxOAuthClient(_SETTINGS)
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

    monkeypatch.setattr(
        client, "_client", lambda: httpx.Client(transport=httpx.MockTransport(handler))
    )
    profile = client.fetch_profile("user-tok")
    assert profile.url_token == "alice"
    assert profile.name == "Alice"
    assert seen["authorization"] == "Bearer platform-secret"
    assert seen["oauth"] == "user-tok"
    assert seen["ts"].isdigit()
