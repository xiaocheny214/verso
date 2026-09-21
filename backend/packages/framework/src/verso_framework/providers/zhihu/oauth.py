"""知乎黑客松 OAuth：授权地址、换票、取名片。凭证不进日志。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from verso_framework.config.app import AppSettings

AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
TOKEN_URL = "https://openapi.zhihu.com/access_token"
PROFILE_URL = "https://openapi.zhihu.com/user"
_ZHIHU_OK = {0, 20000}
_HASH_ID_KEYS = ("hash_id", "hashId", "HashId", "UrlToken", "url_token", "urlToken")
_UID_KEYS = ("uid", "Uid", "UID")
_NAME_KEYS = ("fullname", "Fullname", "Name", "name")
_AVATAR_KEYS = ("avatar_path", "AvatarPath", "avatar_url", "AvatarUrl")
_HEADLINE_KEYS = ("headline", "Headline")
_OPEN_ID_KEYS = ("OpenId", "open_id")

logger = logging.getLogger("verso.zhihu.oauth")
_RETRYABLE = (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout)
_http_lock = threading.Lock()
_http: httpx.Client | None = None
_warmup_started = False


def _shared_http(timeout: float) -> httpx.Client:
    """进程内复用到 openapi.zhihu.com 的 TLS，避免每次登录都握手。"""
    global _http
    with _http_lock:
        if _http is None:
            _http = httpx.Client(
                timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)),
                limits=httpx.Limits(
                    max_keepalive_connections=4,
                    max_connections=8,
                    keepalive_expiry=30.0,
                ),
            )
        return _http


def warm_openapi() -> None:
    """启动时预热 TLS，失败只记日志，不挡进程。"""
    try:
        _shared_http(10.0).post(TOKEN_URL, timeout=5.0)
    except httpx.HTTPError as exc:
        logger.info("zhihu openapi warmup skipped: %s", type(exc).__name__)
    else:
        logger.info("zhihu openapi warmup ok")


def schedule_openapi_warmup() -> None:
    global _warmup_started
    with _http_lock:
        if _warmup_started:
            return
        _warmup_started = True
    threading.Thread(target=warm_openapi, daemon=True, name="zhihu-openapi-warmup").start()


@dataclass(frozen=True, slots=True)
class ZhihuProfile:
    url_token: str
    name: str
    avatar_url: str | None = None
    headline: str | None = None
    open_id: str | None = None


@dataclass(frozen=True, slots=True)
class ZhihuToken:
    access_token: str
    expires_in: int


class OAuthClient(Protocol):
    def authorization_url(self, state: str) -> str: ...

    def exchange_code(self, code: str) -> ZhihuToken: ...

    def fetch_profile(self, access_token: str) -> ZhihuProfile: ...


class HttpxOAuthClient:
    def __init__(
        self,
        settings: AppSettings,
        *,
        timeout: float = 10.0,
        retries: int = 3,
        backoff: float = 0.2,
    ) -> None:
        self._settings = settings
        self._timeout = timeout
        self._retries = max(1, retries)
        self._backoff = backoff

    def authorization_url(self, state: str) -> str:
        query = urlencode(
            {
                "redirect_uri": self._settings.zhihu_redirect_uri,
                "app_id": self._settings.zhihu_client_id,
                "response_type": "code",
                "state": state,
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    def exchange_code(self, code: str) -> ZhihuToken:
        try:
            response = self._request(
                "POST",
                TOKEN_URL,
                data={
                    "app_id": self._settings.zhihu_client_id,
                    "app_key": self._settings.zhihu_client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._settings.zhihu_redirect_uri,
                    "code": code,
                },
            )
        except httpx.HTTPError as exc:
            raise RuntimeError("zhihu token exchange network error") from exc
        if not response.is_success:
            raise RuntimeError(f"zhihu token exchange HTTP {response.status_code}")
        payload = _read_object(response, kind="token exchange")
        blob = _oauth_blob(payload)
        token = blob.get("access_token") or blob.get("AccessToken")
        if not token:
            biz = _biz_code(payload)
            if biz is not None and biz not in _ZHIHU_OK:
                raise RuntimeError(f"zhihu token exchange code={biz}")
            raise RuntimeError("zhihu token exchange failed")
        return ZhihuToken(
            access_token=str(token),
            expires_in=int(blob.get("expires_in") or blob.get("ExpiresIn") or 3600),
        )

    def fetch_profile(self, access_token: str) -> ZhihuProfile:
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            response = self._request("GET", PROFILE_URL, headers=headers)
        except httpx.HTTPError as exc:
            raise RuntimeError("zhihu profile network error") from exc
        if not response.is_success:
            payload = _read_object(response, kind="profile", allow_invalid=True)
            _log_profile_failure(response, payload)
            raise RuntimeError(f"zhihu profile HTTP {response.status_code}")
        if not response.content:
            _log_profile_failure(response, {})
            raise RuntimeError("zhihu profile empty body")
        payload = _read_object(response, kind="profile")
        blobs = _profile_blobs(payload)
        uid = _uid_str(blobs)
        url_token = _first_token(blobs, _HASH_ID_KEYS) or uid
        if url_token:
            return ZhihuProfile(
                url_token=url_token,
                name=_first_token(blobs, _NAME_KEYS) or url_token,
                avatar_url=_first_token(blobs, _AVATAR_KEYS),
                headline=_first_token(blobs, _HEADLINE_KEYS),
                open_id=uid or _first_token(blobs, _OPEN_ID_KEYS),
            )
        _log_profile_failure(response, payload)
        biz = _biz_code(payload)
        if biz is not None and biz not in _ZHIHU_OK:
            raise RuntimeError(f"zhihu profile code={biz}")
        raise RuntimeError(f"zhihu profile missing url_token keys={_key_summary(payload)}")

    def _client(self) -> httpx.Client:
        return _shared_http(self._timeout)

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        client = self._client()
        last: httpx.HTTPError | None = None
        for attempt in range(1, self._retries + 1):
            try:
                return client.request(method, url, **kwargs)
            except _RETRYABLE as exc:
                last = exc
                logger.warning(
                    "zhihu oauth %s attempt=%s/%s %s",
                    method.lower(),
                    attempt,
                    self._retries,
                    type(exc).__name__,
                )
                if attempt >= self._retries:
                    break
                time.sleep(self._backoff * attempt)
        assert last is not None
        raise last


def _read_object(response: httpx.Response, *, kind: str, allow_invalid: bool = False) -> dict:
    if not response.content:
        return {}
    try:
        payload = response.json()
    except ValueError:
        if allow_invalid:
            return {}
        raise RuntimeError(f"zhihu {kind} invalid json") from None
    if not isinstance(payload, dict):
        if allow_invalid:
            return {}
        raise RuntimeError(f"zhihu {kind} not an object")
    return payload


def _oauth_blob(payload: dict) -> dict:
    """顶层或 Data/data 里都可能有业务字段；code:20000 表示成功。"""
    for key in ("Data", "data"):
        inner = payload.get(key)
        if isinstance(inner, dict):
            return {**payload, **inner}
    return payload


def _profile_blobs(payload: dict) -> list[dict]:
    """只展平 Data 和 Data.User，不走进 Items，避免误用他人 UrlToken。"""
    blobs = [payload]
    inner = payload.get("Data")
    if not isinstance(inner, dict):
        inner = payload.get("data")
    if not isinstance(inner, dict):
        return blobs
    blobs.append(inner)
    for key in ("User", "user", "Profile", "profile"):
        nested = inner.get(key)
        if isinstance(nested, dict):
            blobs.append(nested)
    return blobs


def _biz_code(payload: dict) -> int | None:
    raw = payload.get("code", payload.get("Code"))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _first_token(blobs: list[dict], keys: tuple[str, ...]) -> str | None:
    for blob in blobs:
        for key in keys:
            value = blob.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int) and not isinstance(value, bool):
                return str(value)
    return None


def _uid_str(blobs: list[dict]) -> str | None:
    """Keep uid as a decimal string; never round-trip through float."""
    for blob in blobs:
        for key in _UID_KEYS:
            value = blob.get(key)
            if isinstance(value, bool):
                continue
            if isinstance(value, int):
                return str(value)
            if isinstance(value, str) and value.strip().isdigit():
                return value.strip()
    return None


def _key_summary(payload: dict) -> str:
    keys = [str(key) for key in payload]
    data = payload.get("Data", payload.get("data"))
    if isinstance(data, dict):
        keys.extend(f"Data.{key}" for key in data)
        for nest in ("User", "user", "Profile", "profile"):
            nested = data.get(nest)
            if isinstance(nested, dict):
                keys.extend(f"Data.{nest}.{key}" for key in nested)
    return ",".join(keys) if keys else "-"


def _log_profile_failure(response: httpx.Response, payload: dict) -> None:
    data = payload.get("Data", payload.get("data"))
    if isinstance(data, dict):
        data_keys = ",".join(str(key) for key in data)
    elif data is None:
        data_keys = ""
    else:
        data_keys = type(data).__name__
    logger.warning(
        "zhihu profile failed status=%s biz=%s message=%s keys=%s data_keys=%s",
        response.status_code,
        _biz_code(payload),
        _first_str(payload, "Message", "message"),
        ",".join(str(key) for key in payload),
        data_keys,
    )


def _first_str(data: object, *keys: str) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
