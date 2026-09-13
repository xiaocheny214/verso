"""代表授权用户读取创作 / 关注 / 收藏。"""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol

import httpx

from verso_framework.config.app import AppSettings

API_BASE = "https://developer.zhihu.com"


@dataclass(frozen=True, slots=True)
class ZhihuContent:
    title: str
    summary: str
    url: str
    content_type: str
    created_at: int


@dataclass(frozen=True, slots=True)
class ZhihuFollowee:
    fullname: str
    headline: str
    url: str


@dataclass(frozen=True, slots=True)
class ZhihuCollection:
    title: str
    summary: str
    url: str
    fav_time: int


class UserDataClient(Protocol):
    def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]: ...

    def list_followees(self, access_token: str, *, limit: int = 20) -> list[ZhihuFollowee]: ...

    def list_collections(self, access_token: str, *, limit: int = 20) -> list[ZhihuCollection]: ...


class HttpxUserDataClient:
    def __init__(self, settings: AppSettings, *, timeout: float = 10.0) -> None:
        self._settings = settings
        self._timeout = timeout

    def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]:
        payload = self._get(
            "/api/v1/user/contents",
            access_token,
            {"ContentType": "all", "Limit": str(min(limit, 50)), "SortField": "ts"},
        )
        items = []
        for raw in _items(payload):
            items.append(
                ZhihuContent(
                    title=str(raw.get("Title") or ""),
                    summary=str(raw.get("Summary") or ""),
                    url=str(raw.get("Url") or ""),
                    content_type=str(raw.get("ContentType") or ""),
                    created_at=int(raw.get("CreatedAt") or 0),
                )
            )
        return items

    def list_followees(self, access_token: str, *, limit: int = 20) -> list[ZhihuFollowee]:
        payload = self._get(
            "/api/v1/user/followees",
            access_token,
            {"Limit": str(min(limit, 50))},
        )
        items = []
        for raw in _items(payload):
            items.append(
                ZhihuFollowee(
                    fullname=str(raw.get("Fullname") or ""),
                    headline=str(raw.get("Headline") or ""),
                    url=str(raw.get("Url") or ""),
                )
            )
        return items

    def list_collections(self, access_token: str, *, limit: int = 20) -> list[ZhihuCollection]:
        payload = self._get(
            "/api/v1/user/collections",
            access_token,
            {"Limit": str(min(limit, 50))},
        )
        items = []
        for raw in _items(payload):
            items.append(
                ZhihuCollection(
                    title=str(raw.get("Title") or ""),
                    summary=str(raw.get("Summary") or ""),
                    url=str(raw.get("Url") or ""),
                    fav_time=int(raw.get("FavTime") or raw.get("CreatedAt") or 0),
                )
            )
        return items

    def _get(self, path: str, access_token: str, params: dict[str, str]) -> dict:
        headers = {
            "Authorization": f"Bearer {self._settings.zhihu_access_secret}",
            "X-OAuth-Token": access_token,
            "X-Request-Timestamp": str(int(time())),
            "Content-Type": "application/json",
        }
        with httpx.Client(timeout=self._timeout) as client:
            response = client.get(f"{API_BASE}{path}", headers=headers, params=params)
        if not response.content:
            return {}
        payload = response.json()
        return payload if isinstance(payload, dict) else {}


def _items(payload: dict) -> list[dict]:
    data = payload.get("Data")
    if isinstance(data, dict):
        raw_items = data.get("Items")
    else:
        raw_items = payload.get("Items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]
