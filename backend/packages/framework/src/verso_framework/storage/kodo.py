"""七牛云 Kodo 对象存储。"""

from __future__ import annotations

from urllib.parse import quote

import httpx
from qiniu import Auth, BucketManager, put_data

from verso_framework.storage.errors import ObjectStoreError
from verso_framework.storage.ports import StoredObject

_NOT_FOUND = 612


class KodoObjectStore:
    """用 AK/SK 直传和管理空间对象。"""

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        bucket: str,
        domain: str,
        private: bool = True,
        url_expires_sec: int = 3600,
    ) -> None:
        if not access_key or not secret_key or not bucket or not domain:
            raise ObjectStoreError("七牛 Kodo 需要 access_key、secret_key、bucket、domain。")
        self._bucket_name = bucket
        self._domain = domain.rstrip("/")
        self._private = private
        self._url_expires_sec = url_expires_sec
        self._auth = Auth(access_key, secret_key)
        self._bucket = BucketManager(self._auth)

    def put(self, key: str, data: bytes, *, content_type: str = "text/markdown") -> StoredObject:
        token = self._auth.upload_token(self._bucket_name, key)
        ret, info = put_data(token, key, data, mime_type=content_type)
        if ret is None or not info.ok():
            raise ObjectStoreError(f"Kodo 上传失败 key={key}: {info}")
        etag = ret.get("hash") if isinstance(ret, dict) else None
        return StoredObject(key=key, size=len(data), etag=etag)

    def get(self, key: str) -> bytes:
        url = self._download_url(key)
        try:
            response = httpx.get(url, timeout=30.0)
        except httpx.HTTPError as exc:
            raise ObjectStoreError(f"Kodo 下载失败 key={key}: {exc}") from exc
        if response.status_code == 404:
            raise KeyError(key)
        if response.status_code >= 400:
            raise ObjectStoreError(f"Kodo 下载失败 key={key}: HTTP {response.status_code}")
        return response.content

    def delete(self, key: str) -> bool:
        _ret, info = self._bucket.delete(self._bucket_name, key)
        if info.status_code == _NOT_FOUND:
            return False
        if not info.ok():
            raise ObjectStoreError(f"Kodo 删除失败 key={key}: {info}")
        return True

    def exists(self, key: str) -> bool:
        ret, info = self._bucket.stat(self._bucket_name, key)
        if info.status_code == _NOT_FOUND:
            return False
        if not info.ok() or ret is None:
            raise ObjectStoreError(f"Kodo 查询失败 key={key}: {info}")
        return True

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        marker = None
        while True:
            ret, eof, info = self._bucket.list(self._bucket_name, prefix, marker, 1000, None)
            if not info.ok():
                raise ObjectStoreError(f"Kodo 列举失败 prefix={prefix}: {info}")
            items = (ret or {}).get("items") or []
            keys.extend(str(item["key"]) for item in items if "key" in item)
            if eof:
                break
            marker = (ret or {}).get("marker")
            if not marker:
                break
        keys.sort()
        return keys

    def _download_url(self, key: str) -> str:
        base = self._domain
        if not base.startswith(("http://", "https://")):
            base = f"https://{base}"
        url = f"{base}/{quote(key, safe='/')}"
        if self._private:
            return self._auth.private_download_url(url, expires=self._url_expires_sec)
        return url
