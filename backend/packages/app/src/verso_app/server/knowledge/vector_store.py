"""知识库文档向量写入：Milvus 只存向量与定位，不含块明文。

供 knowledge process 编排调用；retrieve search 后做。

物理层：站点一个 collection；``user_id`` 为 partition key（哈希进固定桶，弱隔离）；
``user_id`` / ``knowledge_base_id`` / ``document_id`` 建 INVERTED；读写 filter 必带
``user_id``。可选 ``metadata`` JSON 仅放展示快照，禁止 chunk 明文。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pymilvus import DataType, MilvusClient

from verso_framework.config.milvus import get_milvus_settings
from verso_framework.vector import get_milvus_client

_ID_MAX = 64
_UUID_MAX = 36
_FORBIDDEN_METADATA_KEYS = frozenset({"text", "content", "embedding_text", "body"})


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
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def point_id(self) -> str:
        return f"{self.document_id}:{self.chunk_index}"


def _scrub_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in metadata.items() if key not in _FORBIDDEN_METADATA_KEYS}
    if any(key in metadata for key in _FORBIDDEN_METADATA_KEYS):
        raise ValueError("metadata must not contain chunk plaintext keys")
    return clean


def _document_filter(*, user_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f'user_id == "{user_id}" and document_id == "{document_id}"'


@runtime_checkable
class ChunkVectorStore(Protocol):
    def ensure_collection(self, *, dimension: int) -> None: ...

    def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None: ...

    def upsert(self, points: list[ChunkVectorPoint]) -> None: ...

    def list_document_ids(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> list[str]:
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

    def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        prefix = f"{document_id}:"
        for key in [
            k
            for k, point in self._points.items()
            if k.startswith(prefix) and point.user_id == user_id
        ]:
            del self._points[key]

    def upsert(self, points: list[ChunkVectorPoint]) -> None:
        for point in points:
            _scrub_metadata(point.metadata)
            if self._dimension is not None and len(point.embedding) != self._dimension:
                raise ValueError("embedding dimension mismatch")
            self._points[point.point_id] = point

    def list_document_ids(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> list[str]:
        prefix = f"{document_id}:"
        return sorted(
            k
            for k, point in self._points.items()
            if k.startswith(prefix) and point.user_id == user_id
        )


class MilvusChunkVectorStore:
    """站点物理 collection；partition key = user_id；标量倒排；无 content。"""

    def __init__(
        self,
        client: MilvusClient | None = None,
        *,
        collection: str | None = None,
        num_partitions: int | None = None,
    ) -> None:
        self._client = client
        self._collection = collection
        self._num_partitions = num_partitions

    def _resolved(self) -> tuple[MilvusClient, str, int]:
        client = self._client if self._client is not None else get_milvus_client()
        settings = get_milvus_settings()
        name = self._collection if self._collection is not None else settings.collection
        partitions = (
            self._num_partitions if self._num_partitions is not None else settings.num_partitions
        )
        return client, name, partitions

    def ensure_collection(self, *, dimension: int) -> None:
        if dimension < 1:
            raise ValueError("dimension must be >= 1")
        client, name, num_partitions = self._resolved()
        if client.has_collection(collection_name=name):
            return
        if num_partitions < 1:
            raise ValueError("num_partitions must be >= 1")

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(
            field_name="id",
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=_ID_MAX,
        )
        schema.add_field(
            field_name="user_id",
            datatype=DataType.VARCHAR,
            max_length=_UUID_MAX,
            is_partition_key=True,
        )
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
        schema.add_field(field_name="metadata", datatype=DataType.JSON)
        schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=dimension)

        index_params = client.prepare_index_params()
        index_params.add_index(field_name="user_id", index_type="INVERTED")
        index_params.add_index(field_name="knowledge_base_id", index_type="INVERTED")
        index_params.add_index(field_name="document_id", index_type="INVERTED")
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 48, "efConstruction": 200},
        )
        client.create_collection(
            collection_name=name,
            schema=schema,
            index_params=index_params,
            num_partitions=num_partitions,
        )

    def delete_document(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> None:
        client, name, _partitions = self._resolved()
        if not client.has_collection(collection_name=name):
            return
        client.delete(
            collection_name=name,
            filter=_document_filter(user_id=user_id, document_id=document_id),
        )

    def upsert(self, points: list[ChunkVectorPoint]) -> None:
        if not points:
            return
        client, name, _partitions = self._resolved()
        rows = [
            {
                "id": point.point_id,
                "user_id": str(point.user_id),
                "knowledge_base_id": str(point.knowledge_base_id),
                "document_id": str(point.document_id),
                "chunk_index": point.chunk_index,
                "char_start": point.char_start,
                "char_end": point.char_end,
                "metadata": _scrub_metadata(point.metadata),
                "embedding": point.embedding,
            }
            for point in points
        ]
        client.upsert(collection_name=name, data=rows)

    def list_document_ids(self, *, user_id: uuid.UUID, document_id: uuid.UUID) -> list[str]:
        client, name, _partitions = self._resolved()
        if not client.has_collection(collection_name=name):
            return []
        rows = client.query(
            collection_name=name,
            filter=_document_filter(user_id=user_id, document_id=document_id),
            output_fields=["id"],
        )
        return sorted(str(row["id"]) for row in rows)
