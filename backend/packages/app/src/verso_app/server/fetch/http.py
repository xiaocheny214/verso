"""用知乎内容接口取 HTML，再转 Markdown。"""

from __future__ import annotations

import httpx

from verso_app.server.fetch.errors import FetchError
from verso_app.server.fetch.html import html_to_markdown
from verso_app.server.fetch.ports import FetchedMarkdown
from verso_app.server.fetch.urls import ArchivableUrl

_API_ROOT = "https://www.zhihu.com/api/v4"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.zhihu.com/",
}


class HttpxZhihuMarkdownFetcher:
    """只抓单篇专栏或回答。不下载图片，Markdown 里保留原图链接。"""

    def __init__(self, *, timeout: float = 20.0, client: httpx.Client | None = None) -> None:
        self._timeout = timeout
        self._client = client

    def fetch(self, target: ArchivableUrl) -> FetchedMarkdown:
        if self._client is not None:
            return self._fetch_with(self._client, target)
        with httpx.Client(timeout=self._timeout, headers=_HEADERS, follow_redirects=True) as client:
            return self._fetch_with(client, target)

    def _fetch_with(self, client: httpx.Client, target: ArchivableUrl) -> FetchedMarkdown:
        if target.kind == "article":
            payload = self._get(client, f"{_API_ROOT}/articles/{target.content_id}")
            title = str(payload.get("title") or "")
            html = str(payload.get("content") or "")
        else:
            payload = self._get(
                client,
                f"{_API_ROOT}/answers/{target.content_id}",
                params={"include": "content,question"},
            )
            question = payload.get("question") if isinstance(payload.get("question"), dict) else {}
            title = str(question.get("title") or payload.get("title") or "")
            html = str(payload.get("content") or "")
        markdown = html_to_markdown(html)
        if not markdown:
            raise FetchError(f"empty markdown url={target.source_url}")
        return FetchedMarkdown(
            source_url=target.source_url,
            content_type=target.kind,
            title=title,
            markdown=markdown,
        )

    def _get(
        self,
        client: httpx.Client,
        url: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict:
        try:
            response = client.get(url, params=params, headers=_HEADERS)
        except httpx.HTTPError as exc:
            raise FetchError(f"network error url={url}: {exc}") from exc
        if response.status_code >= 400:
            raise FetchError(f"http {response.status_code} url={url}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise FetchError(f"invalid json url={url}") from exc
        if not isinstance(payload, dict):
            raise FetchError(f"unexpected payload url={url}")
        error = payload.get("error")
        if isinstance(error, dict):
            raise FetchError(f"zhihu error url={url}: {error.get('message') or error}")
        return payload
