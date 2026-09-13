"""知乎黑客松 OAuth：授权地址、换票、取名片。凭证不进日志。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from verso_framework.config.app import AppSettings

AUTHORIZE_URL = "https://openapi.zhihu.com/authorize"
TOKEN_URL = "https://openapi.zhihu.com/access_token"
PROFILE_URL = "https://developer.zhihu.com/api/v1/user"


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
        with httpx.Client(timeout=self._timeout) as client:
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
        payload = response.json() if response.content else {}
        token = payload.get("access_token")
        if not token:
            raise RuntimeError("zhihu token exchange failed")
        return ZhihuToken(
            access_token=str(token),
            expires_in=int(payload.get("expires_in") or 3600),
        )

    def fetch_profile(self, access_token: str) -> ZhihuProfile:
        headers = {
            "Authorization": f"Bearer {self._settings.zhihu_access_secret}",
            "X-OAuth-Token": access_token,
            "X-Request-Timestamp": str(_unix_now()),
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(PROFILE_URL, headers=headers)
        payload = response.json() if response.content else {}
        data = payload.get("Data") if isinstance(payload.get("Data"), dict) else payload
        url_token = _first_str(data, "UrlToken", "url_token")
        name = _first_str(data, "Fullname", "Name", "name") or url_token
        if not url_token:
            raise RuntimeError("zhihu profile missing url_token")
        return ZhihuProfile(
            url_token=url_token,
            name=name,
            avatar_url=_first_str(data, "AvatarUrl", "avatar_url"),
            headline=_first_str(data, "Headline", "headline"),
            open_id=_first_str(data, "OpenId", "open_id", "id"),
        )


def _unix_now() -> int:
    from time import time

    return int(time())


def _first_str(data: object, *keys: str) -> str | None:
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return None
