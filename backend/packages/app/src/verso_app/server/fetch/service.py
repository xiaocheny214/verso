"""独立抓取模块：校验链接，取正文，转成 Markdown。不写库、不上对象存储。"""

from __future__ import annotations

from verso_app.server.fetch.errors import FetchError
from verso_app.server.fetch.ports import FetchedMarkdown, MarkdownFetcher
from verso_app.server.fetch.urls import ArchivableUrl, parse_archivable_url


class FetchService:
    def __init__(self, backend: MarkdownFetcher) -> None:
        self._backend = backend

    def fetch(self, url: str) -> FetchedMarkdown:
        target = parse_archivable_url(url)
        if target is None:
            raise FetchError("not an article or answer url")
        return self._backend.fetch(target)

    def fetch_target(self, target: ArchivableUrl) -> FetchedMarkdown:
        return self._backend.fetch(target)
