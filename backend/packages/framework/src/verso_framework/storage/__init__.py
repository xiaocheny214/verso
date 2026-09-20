"""对象存储端口。生产走七牛云 Kodo；测试可注入内存实现。"""

from verso_framework.storage.errors import ObjectStoreError
from verso_framework.storage.factory import build_object_store, get_object_store
from verso_framework.storage.kodo import KodoObjectStore
from verso_framework.storage.memory import MemoryObjectStore
from verso_framework.storage.ports import ObjectStore, StoredObject

__all__ = [
    "KodoObjectStore",
    "MemoryObjectStore",
    "ObjectStore",
    "ObjectStoreError",
    "StoredObject",
    "build_object_store",
    "get_object_store",
]
