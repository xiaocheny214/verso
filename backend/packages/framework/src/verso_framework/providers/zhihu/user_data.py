"""代表授权用户读取创作 / 关注 / 收藏。

开放接口没有「我点过赞」的列表；兴趣信号用近期收藏和收藏夹内容。
HTTP 非 2xx，或业务码既不是文档约定的 0、也不是 OAuth 实测的 20000 时抛错。
只有成功且 Items 为空才返回空列表。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from time import time
from typing import Protocol

import httpx

from verso_framework.config.app import AppSettings

API_BASE = "https://developer.zhihu.com"
_FAVLIST_SCAN = 3
# user-api.md / http-api.md 成功码是 Code:0；OAuth 名片实测还有 lowercase code:20000。
_ZHIHU_OK = frozenset({0, 20000})

logger = logging.getLogger("verso.zhihu.user_data")
_http_lock = threading.Lock()
_http: httpx.Client | None = None


def _shared_http(timeout: float) -> httpx.Client:
    """进程内复用到 developer.zhihu.com 的 TLS，避免画像拉取每次握手。"""
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


class ZhihuUserDataError(RuntimeError):
    """网络、HTTP、业务码失败，区别于成功的空 Items。"""


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
        try:
            favlists = self._favlists(access_token)
        except ZhihuUserDataError:
            favlists = []
        for favlist in favlists[:_FAVLIST_SCAN]:
            token = favlist.get("UrlToken")
            try:
                token_int = int(token)
            except (TypeError, ValueError):
                continue
            list_title = str(favlist.get("Title") or "")
            try:
                extras = self._favlist_contents(access_token, token_int)
            except ZhihuUserDataError:
                continue
            for item in extras:
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

    def _client(self) -> httpx.Client:
        return _shared_http(self._timeout)

    def _get(self, path: str, access_token: str, params: dict[str, str]) -> dict:
        headers = {
            "Authorization": f"Bearer {self._settings.zhihu_access_secret}",
            "X-OAuth-Token": access_token,
            "X-Request-Timestamp": str(int(time())),
            "Content-Type": "application/json",
        }
        try:
            response = self._client().get(f"{API_BASE}{path}", headers=headers, params=params)
        except httpx.HTTPError as exc:
            raise ZhihuUserDataError(f"zhihu GET {path} network error") from exc
        if not response.is_success:
            raise ZhihuUserDataError(f"zhihu GET {path} HTTP {response.status_code}")
        if not response.content:
            raise ZhihuUserDataError(f"zhihu GET {path} empty body")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ZhihuUserDataError(f"zhihu GET {path} invalid json") from exc
        if not isinstance(payload, dict):
            raise ZhihuUserDataError(f"zhihu GET {path} not an object")
        code = _biz_code(payload)
        if not _zhihu_ok(code):
            keys = ",".join(sorted(str(key) for key in payload))
            raise ZhihuUserDataError(f"zhihu GET {path} code={code} keys={keys}")
        return payload


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


def _biz_code(payload: dict) -> object:
    if "code" in payload:
        return payload.get("code")
    return payload.get("Code")


def _zhihu_ok(code: object) -> bool:
    try:
        return int(code) in _ZHIHU_OK
    except (TypeError, ValueError):
        return False


def _items(payload: dict) -> list[dict]:
    data = payload.get("Data")
    if not isinstance(data, dict):
        data = payload.get("data")
    if isinstance(data, dict) and ("Items" in data or "items" in data):
        raw_items = data["Items"] if "Items" in data else data.get("items")
    elif "Items" in payload:
        raw_items = payload["Items"]
    elif "items" in payload:
        raw_items = payload["items"]
    else:
        raise ZhihuUserDataError("zhihu payload missing Items")
    if not isinstance(raw_items, list):
        raise ZhihuUserDataError("zhihu Items is not a list")
    return [item for item in raw_items if isinstance(item, dict)]
