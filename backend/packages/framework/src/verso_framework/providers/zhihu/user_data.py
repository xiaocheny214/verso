"""代表授权用户读取创作 / 关注 / 收藏。

开放接口没有「我点过赞」的列表；兴趣信号用近期收藏和收藏夹内容。
某一路失败返回空列表，不拖垮其它路。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Protocol

import httpx

from verso_framework.config.app import AppSettings

API_BASE = "https://developer.zhihu.com"
_FAVLIST_SCAN = 3


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
    extra_text: str = ""


class UserDataClient(Protocol):
    def list_contents(self, access_token: str, *, limit: int = 50) -> list[ZhihuContent]: ...

    def list_followees(self, access_token: str, *, limit: int = 20) -> list[ZhihuFollowee]: ...

    def list_favorites(self, access_token: str, *, limit: int = 50) -> list[ZhihuCollection]: ...


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

    def list_favorites(self, access_token: str, *, limit: int = 50) -> list[ZhihuCollection]:
        """近期收藏 + 少量公开收藏夹内容。没有点赞时间线接口。"""
        found: list[ZhihuCollection] = []
        seen: set[str] = set()
        for item in self._collections(access_token, limit=limit):
            _push_unique(found, seen, item)
        for favlist in self._favlists(access_token)[:_FAVLIST_SCAN]:
            token = favlist.get("UrlToken")
            try:
                token_int = int(token)
            except (TypeError, ValueError):
                continue
            list_title = str(favlist.get("Title") or "")
            for item in self._favlist_contents(access_token, token_int):
                if list_title:
                    item = ZhihuCollection(
                        title=item.title,
                        summary=item.summary,
                        url=item.url,
                        fav_time=item.fav_time,
                        extra_text=list_title,
                    )
                _push_unique(found, seen, item)
        return found[:limit]

    def _collections(self, access_token: str, *, limit: int) -> list[ZhihuCollection]:
        payload = self._get(
            "/api/v1/user/collections",
            access_token,
            {"Limit": str(min(limit, 50))},
        )
        return [_collection_from_raw(raw) for raw in _items(payload)]

    def _favlists(self, access_token: str) -> list[dict]:
        payload = self._get("/api/v1/user/favlists", access_token, {"Limit": "20"})
        return _items(payload)

    def _favlist_contents(self, access_token: str, url_token: int) -> list[ZhihuCollection]:
        payload = self._get(
            "/api/v1/user/favlist_contents",
            access_token,
            {"FavlistUrlToken": str(url_token), "Limit": "20"},
        )
        return [_collection_from_raw(raw) for raw in _items(payload)]

    def _get(self, path: str, access_token: str, params: dict[str, str]) -> dict:
        headers = {
            "Authorization": f"Bearer {self._settings.zhihu_access_secret}",
            "X-OAuth-Token": access_token,
            "X-Request-Timestamp": str(int(time())),
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.get(f"{API_BASE}{path}", headers=headers, params=params)
            if not response.content:
                return {}
            payload = response.json()
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}


def _collection_from_raw(raw: dict) -> ZhihuCollection:
    extra = ""
    favlists = raw.get("Favlists")
    if isinstance(favlists, list):
        titles = [
            str(item.get("Title") or "")
            for item in favlists
            if isinstance(item, dict) and item.get("Title")
        ]
        extra = " ".join(titles)
    return ZhihuCollection(
        title=str(raw.get("Title") or ""),
        summary=str(raw.get("Summary") or ""),
        url=str(raw.get("Url") or ""),
        fav_time=int(raw.get("FavTime") or raw.get("CreatedAt") or 0),
        extra_text=extra,
    )


def _push_unique(found: list[ZhihuCollection], seen: set[str], item: ZhihuCollection) -> None:
    key = item.url or f"{item.title}:{item.fav_time}"
    if key in seen:
        return
    seen.add(key)
    found.append(item)


def _items(payload: dict) -> list[dict]:
    data = payload.get("Data")
    if isinstance(data, dict):
        raw_items = data.get("Items")
    else:
        raw_items = payload.get("Items")
    if not isinstance(raw_items, list):
        return []
    return [item for item in raw_items if isinstance(item, dict)]
