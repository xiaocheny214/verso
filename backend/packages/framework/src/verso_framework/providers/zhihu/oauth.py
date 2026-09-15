"""知乎黑客松 OAuth：授权地址、换票、取名片。凭证不进日志。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from verso_framework.config.app import AppSettings

AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
TOKEN_URL = "https://openapi.zhihu.com/access_token"
PROFILE_URL = "https://developer.zhihu.com/api/v1/user"
_ZHIHU_OK = {0, 20000}
_URL_TOKEN_KEYS = ("UrlToken", "url_token", "urlToken")
_NAME_KEYS = ("Fullname", "Name", "name", "fullname")
_AVATAR_KEYS = ("AvatarUrl", "avatar_url")
_HEADLINE_KEYS = ("Headline", "headline")
_OPEN_ID_KEYS = ("OpenId", "open_id")

logger = logging.getLogger("verso.zhihu.oauth")


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
    def __init__(self, settings: AppSettings, *, timeout: float = 10.0) -> None:
        self._settings = settings
        self._timeout = timeout

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
            with self._client() as client:
                response = client.post(
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
        headers = {
            "Authorization": f"Bearer {self._settings.zhihu_access_secret}",
            "X-OAuth-Token": access_token,
            "X-Request-Timestamp": str(_unix_now()),
            "Content-Type": "application/json",
        }
        try:
            with self._client() as client:
                response = client.get(PROFILE_URL, headers=headers)
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
        url_token = _first_token(blobs, _URL_TOKEN_KEYS)
        if url_token:
            return ZhihuProfile(
                url_token=url_token,
                name=_first_token(blobs, _NAME_KEYS) or url_token,
                avatar_url=_first_token(blobs, _AVATAR_KEYS),
                headline=_first_token(blobs, _HEADLINE_KEYS),
                open_id=_first_token(blobs, _OPEN_ID_KEYS),
            )
        _log_profile_failure(response, payload)
        biz = _biz_code(payload)
        if biz is not None and biz not in _ZHIHU_OK:
            raise RuntimeError(f"zhihu profile code={biz}")
        raise RuntimeError(f"zhihu profile missing url_token keys={_key_summary(payload)}")

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout)


def _unix_now() -> int:
    from time import time

    return int(time())


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
