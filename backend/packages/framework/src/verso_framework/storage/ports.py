"""对象存储端口。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StoredObject:
    """已写入对象的摘要。"""

    key: str
    size: int
    etag: str | None = None


class ObjectStore(Protocol):
    """按 key 上传、读取、删除、查询对象。"""

    def put(self, key: str, data: bytes, *, content_type: str = "text/markdown") -> StoredObject:
        """覆盖写入。"""

    def get(self, key: str) -> bytes:
        """读取对象正文。不存在则 ``KeyError``。"""

    def delete(self, key: str) -> bool:
        """删除。已不存在时返回 ``False``。"""

    def exists(self, key: str) -> bool:
        """对象是否存在。"""

    def list_keys(self, prefix: str) -> list[str]:
        """列出前缀下的 key，按字典序。"""
