"""抓取端口：一条链接变成 Markdown。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from verso_app.server.fetch.urls import ArchivableUrl, Kind


@dataclass(frozen=True, slots=True)
class FetchedMarkdown:
    source_url: str
    content_type: Kind
    title: str
    markdown: str


class MarkdownFetcher(Protocol):
    def fetch(self, target: ArchivableUrl) -> FetchedMarkdown:
        """拉取正文并转成 Markdown。失败抛 ``FetchError``。"""
