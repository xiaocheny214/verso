"""只收授权用户创作列表里的专栏和单条回答。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

Kind = Literal["article", "answer"]

_ARTICLE = re.compile(r"^/p/(\d+)/?$")
_ANSWER_ON_QUESTION = re.compile(r"^/question/\d+/answer/(\d+)/?$")
_ANSWER_SHORT = re.compile(r"^/answer/(\d+)/?$")
_SKIP_TYPES = frozenset({"pin", "zvideo", "question", "collection", "favlist"})


@dataclass(frozen=True, slots=True)
class ArchivableUrl:
    kind: Kind
    content_id: str
    source_url: str


def parse_archivable_url(url: str) -> ArchivableUrl | None:
    raw = (url or "").strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host in {"zhuanlan.zhihu.com", "www.zhuanlan.zhihu.com"}:
        match = _ARTICLE.match(path)
        if match:
            return ArchivableUrl(kind="article", content_id=match.group(1), source_url=raw)
        return None
    if host in {"www.zhihu.com", "zhihu.com"}:
        match = _ANSWER_ON_QUESTION.match(path) or _ANSWER_SHORT.match(path)
        if match:
            return ArchivableUrl(kind="answer", content_id=match.group(1), source_url=raw)
        return None
    return None


def archivable_from_content(*, url: str, content_type: str) -> ArchivableUrl | None:
    """列表类型不是专栏/回答则跳过；URL 必须能解析成单篇。"""
    kind = (content_type or "").strip().lower()
    if kind in _SKIP_TYPES:
        return None
    target = parse_archivable_url(url)
    if target is None:
        return None
    if kind and kind not in {"article", "answer", "all", ""} and kind != target.kind:
        return None
    return target
