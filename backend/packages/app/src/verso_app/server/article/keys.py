"""对象键：按用户隔离一篇 Markdown。"""

from __future__ import annotations

import hashlib
import uuid


def article_object_key(user_id: uuid.UUID, source_url: str, *, prefix: str = "articles") -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}/{user_id}/{digest}.md"


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
