"""进程内对象存储，供测试注入。"""

from __future__ import annotations

from verso_framework.storage.ports import StoredObject


class MemoryObjectStore:
    """不访问网络的 dict 后端。"""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    def put(self, key: str, data: bytes, *, content_type: str = "text/markdown") -> StoredObject:
        del content_type
        self._objects[key] = data
        return StoredObject(key=key, size=len(data), etag=None)

    def get(self, key: str) -> bytes:
        try:
            return self._objects[key]
        except KeyError:
            raise KeyError(key) from None

    def delete(self, key: str) -> bool:
        return self._objects.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        return key in self._objects

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self._objects if key.startswith(prefix))
