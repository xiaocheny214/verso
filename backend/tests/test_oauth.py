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


def test_fetch_profile_uses_openapi_oauth_bearer(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["path"] = request.url.path
        seen["authorization"] = request.headers["Authorization"]
        seen["oauth"] = request.headers.get("X-OAuth-Token", "")
        seen["ts"] = request.headers.get("X-Request-Timestamp", "")
        return httpx.Response(
            200,
            json={
                "uid": 969570047710216200,
                "hash_id": "alice",
                "fullname": "Alice",
                "avatar_path": "https://x/a.png",
                "headline": "dev",
                "email": "alice@example.com",
                "phone_no": "13800000000",
            },
        )

    profile = _client(monkeypatch, handler).fetch_profile("user-tok")
    assert profile.url_token == "alice"
    assert profile.name == "Alice"
    assert profile.avatar_url == "https://x/a.png"
    assert profile.headline == "dev"
    assert profile.open_id == "969570047710216200"
    assert seen["host"] == "openapi.zhihu.com"
    assert seen["path"] == "/user"
    assert seen["authorization"] == "Bearer user-tok"
    assert seen["oauth"] == ""
    assert seen["ts"] == ""


def test_fetch_profile_falls_back_to_uid_when_hash_id_missing(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"uid": 12345, "fullname": "Alice"})

    profile = _client(monkeypatch, handler).fetch_profile("user-tok")
    assert profile.url_token == "12345"
    assert profile.open_id == "12345"


def test_fetch_profile_accepts_wrapped_user_object(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 20000, "Data": {"User": {"hash_id": "alice", "fullname": "Alice"}}},
        )

    profile = _client(monkeypatch, handler).fetch_profile("user-tok")
    assert profile.url_token == "alice"
    assert profile.name == "Alice"


def test_fetch_profile_http_error_is_not_missing_token(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"")

    with pytest.raises(RuntimeError, match="zhihu profile HTTP 404"):
        _client(monkeypatch, handler).fetch_profile("user-tok")


def test_fetch_profile_biz_error_is_not_missing_token(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 404, "data": "User don't exist"})

    with pytest.raises(RuntimeError, match="zhihu profile code=404"):
        _client(monkeypatch, handler).fetch_profile("user-tok")


def test_fetch_profile_open_id_without_user_id_still_fails(monkeypatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 20000, "Data": {"OpenId": "x"}})

    with pytest.raises(RuntimeError, match="zhihu profile missing url_token keys="):
        _client(monkeypatch, handler).fetch_profile("user-tok")


class _FlakyClient:
    def __init__(self, failures: int, response: httpx.Response) -> None:
        self._left = failures
        self._response = response
        self.calls = 0

    def request(self, _method: str, _url: str, **_kwargs) -> httpx.Response:
        self.calls += 1
        if self._left > 0:
            self._left -= 1
            raise httpx.ConnectTimeout("tls handshake")
        return self._response


def test_fetch_profile_retries_connect_timeout(monkeypatch) -> None:
    monkeypatch.setattr("verso_framework.providers.zhihu.oauth.time.sleep", lambda _s: None)
    flaky = _FlakyClient(
        2,
        httpx.Response(200, json={"uid": 1, "hash_id": "alice", "fullname": "Alice"}),
    )
    client = HttpxOAuthClient(_SETTINGS)
    monkeypatch.setattr(client, "_client", lambda: flaky)
    profile = client.fetch_profile("user-tok")
    assert profile.url_token == "alice"
    assert flaky.calls == 3


def test_fetch_profile_connect_timeout_exhausted(monkeypatch) -> None:
    monkeypatch.setattr("verso_framework.providers.zhihu.oauth.time.sleep", lambda _s: None)
    flaky = _FlakyClient(9, httpx.Response(200, json={"uid": 1, "hash_id": "alice"}))
    client = HttpxOAuthClient(_SETTINGS, retries=3)
    monkeypatch.setattr(client, "_client", lambda: flaky)
    with pytest.raises(RuntimeError, match="zhihu profile network error"):
        client.fetch_profile("user-tok")
    assert flaky.calls == 3


def test_exchange_code_retries_connect_timeout(monkeypatch) -> None:
    monkeypatch.setattr("verso_framework.providers.zhihu.oauth.time.sleep", lambda _s: None)
    flaky = _FlakyClient(
        1,
        httpx.Response(
            200,
            json={"code": 20000, "Data": {"access_token": "user-tok", "expires_in": 3600}},
        ),
    )
    client = HttpxOAuthClient(_SETTINGS)
    monkeypatch.setattr(client, "_client", lambda: flaky)
    token = client.exchange_code("from-callback")
    assert token.access_token == "user-tok"
    assert flaky.calls == 2
