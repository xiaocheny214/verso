"""知识库文档向量写入：Milvus 只存向量与定位，不含块明文。

供 knowledge process 编排调用；retrieve search 后做。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pymilvus import DataType, MilvusClient

from verso_framework.config.milvus import get_milvus_settings
from verso_framework.vector import get_milvus_client

_ID_MAX = 64
_UUID_MAX = 36


@dataclass(frozen=True, slots=True)
class ChunkVectorPoint:
    """一条可 upsert 的块向量（无 text）。"""

    user_id: uuid.UUID
    knowledge_base_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    char_start: int
    char_end: int
    embedding: list[float]

    @property
    def point_id(self) -> str:
        return f"{self.document_id}:{self.chunk_index}"


@runtime_checkable
class ChunkVectorStore(Protocol):
    def ensure_collection(self, *, dimension: int) -> None: ...

    def delete_document(self, *, document_id: uuid.UUID) -> None: ...

    def upsert(self, points: list[ChunkVectorPoint]) -> None: ...

    def list_document_ids(self, *, document_id: uuid.UUID) -> list[str]:
        """测试/观测用：列出该文档已写入的点 id。"""


class MemoryChunkVectorStore:
    """进程内假实现，供单测。"""

    def __init__(self) -> None:
        self._dimension: int | None = None
        self._points: dict[str, ChunkVectorPoint] = {}

    def ensure_collection(self, *, dimension: int) -> None:
        if dimension < 1:
            raise ValueError("dimension must be >= 1")
        if self._dimension is None:
            self._dimension = dimension
        elif self._dimension != dimension:
            raise ValueError(
                f"collection dimension mismatch: have {self._dimension}, got {dimension}"
            )

    def delete_document(self, *, document_id: uuid.UUID) -> None:
        prefix = f"{document_id}:"
        for key in [k for k in self._points if k.startswith(prefix)]:
            del self._points[key]

    def upsert(self, points: list[ChunkVectorPoint]) -> None:
        for point in points:
            if self._dimension is not None and len(point.embedding) != self._dimension:
                raise ValueError("embedding dimension mismatch")
            self._points[point.point_id] = point

    def list_document_ids(self, *, document_id: uuid.UUID) -> list[str]:
        prefix = f"{document_id}:"
        return sorted(k for k in self._points if k.startswith(prefix))


class MilvusChunkVectorStore:
    """站点物理 collection；标量含租户与偏移，无 content。"""

    def __init__(
        self,
        client: MilvusClient | None = None,
        *,
        collection: str | None = None,
    ) -> None:
        self._client = client
        self._collection = collection

    def _resolved(self) -> tuple[MilvusClient, str]:
        client = self._client if self._client is not None else get_milvus_client()
        name = (
            self._collection if self._collection is not None else get_milvus_settings().collection
        )
        return client, name

    def ensure_collection(self, *, dimension: int) -> None:
        if dimension < 1:
            raise ValueError("dimension must be >= 1")
        client, name = self._resolved()
        if client.has_collection(collection_name=name):
            return
        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=_ID_MAX,
        )
        schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=_UUID_MAX)
        schema.add_field(
            field_name="knowledge_base_id",
            datatype=DataType.VARCHAR,
            max_length=_UUID_MAX,
        )
        schema.add_field(
            field_name="document_id",
            datatype=DataType.VARCHAR,
            max_length=_UUID_MAX,
        )
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
        schema.add_field(field_name="char_start", datatype=DataType.INT64)
        schema.add_field(field_name="char_end", datatype=DataType.INT64)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dimension)
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="AUTOINDEX",
            metric_type="COSINE",
        )
        client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
        )

    def delete_document(self, *, document_id: uuid.UUID) -> None:
        client, name = self._resolved()
        if not client.has_collection(collection_name=name):
            return
        client.delete(
            collection_name=name,
            filter=f'document_id == "{document_id}"',
        )

    def upsert(self, points: list[ChunkVectorPoint]) -> None:
        if not points:
            return
        client, name = self._resolved()
        rows = [
            {
                "id": point.point_id,
                "user_id": str(point.user_id),
                "knowledge_base_id": str(point.knowledge_base_id),
                "document_id": str(point.document_id),
                "chunk_index": point.chunk_index,
                "char_start": point.char_start,
                "char_end": point.char_end,
                "embedding": point.embedding,
            }
            for point in points
        ]
        client.upsert(collection_name=name, data=rows)

    def list_document_ids(self, *, document_id: uuid.UUID) -> list[str]:
        client, name = self._resolved()
        if not client.has_collection(collection_name=name):
            return []
        rows = client.query(
            collection_name=name,
            filter=f'document_id == "{document_id}"',
            output_fields=["id"],
        )
        return sorted(str(row["id"]) for row in rows)
