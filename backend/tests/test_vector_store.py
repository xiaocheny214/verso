from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from verso_app.server.knowledge.vector_store import (
    ChunkVectorPoint,
    MemoryChunkVectorStore,
    MilvusChunkVectorStore,
)


def test_memory_store_rejects_plaintext_metadata_keys() -> None:
    store = MemoryChunkVectorStore()
    store.ensure_collection(dimension=4)
    point = ChunkVectorPoint(
        user_id=uuid.uuid4(),
        knowledge_base_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        char_start=0,
        char_end=1,
        embedding=[0.1, 0.2, 0.3, 0.4],
        metadata={"text": "secret"},
    )
    with pytest.raises(ValueError, match="plaintext"):
        store.upsert([point])


def test_memory_store_scopes_delete_and_list_by_user() -> None:
    store = MemoryChunkVectorStore()
    store.ensure_collection(dimension=2)
    owner = uuid.uuid4()
    other = uuid.uuid4()
    doc = uuid.uuid4()
    kb = uuid.uuid4()
    store.upsert(
        [
            ChunkVectorPoint(
                user_id=owner,
                knowledge_base_id=kb,
                document_id=doc,
                chunk_index=0,
                char_start=0,
                char_end=1,
                embedding=[1.0, 0.0],
                metadata={"title": "a"},
            )
        ]
    )
    store.delete_document(user_id=other, document_id=doc)
    assert store.list_document_ids(user_id=owner, document_id=doc) == [f"{doc}:0"]
    store.delete_document(user_id=owner, document_id=doc)
    assert store.list_document_ids(user_id=owner, document_id=doc) == []


def test_milvus_ensure_collection_builds_inverted_and_partition() -> None:
    client = MagicMock()
    client.has_collection.return_value = False
    index_params = MagicMock()
    client.prepare_index_params.return_value = index_params
    schema = MagicMock()
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "verso_app.server.knowledge.vector_store.MilvusClient.create_schema",
            MagicMock(return_value=schema),
        )
        store = MilvusChunkVectorStore(client, collection="verso_chunks", num_partitions=64)
        store.ensure_collection(dimension=8)

    field_names = [call.kwargs["field_name"] for call in schema.add_field.call_args_list]
    assert field_names == [
        "id",
        "user_id",
        "knowledge_base_id",
        "document_id",
        "chunk_index",
        "char_start",
        "char_end",
        "metadata",
        "embedding",
    ]
    user_field = next(
        call.kwargs
        for call in schema.add_field.call_args_list
        if call.kwargs["field_name"] == "user_id"
    )
    assert user_field["is_partition_key"] is True

    index_fields = [call.kwargs["field_name"] for call in index_params.add_index.call_args_list]
    assert index_fields == ["user_id", "knowledge_base_id", "document_id", "embedding"]
    inverted = [
        call.kwargs
        for call in index_params.add_index.call_args_list
        if call.kwargs["index_type"] == "INVERTED"
    ]
    assert {item["field_name"] for item in inverted} == {
        "user_id",
        "knowledge_base_id",
        "document_id",
    }
    embedding_index = next(
        call.kwargs
        for call in index_params.add_index.call_args_list
        if call.kwargs["field_name"] == "embedding"
    )
    assert embedding_index["index_type"] == "HNSW"
    assert embedding_index["metric_type"] == "COSINE"
    assert embedding_index["params"] == {"M": 48, "efConstruction": 200}

    client.create_collection.assert_called_once()
    create_kwargs = client.create_collection.call_args.kwargs
    assert create_kwargs["collection_name"] == "verso_chunks"
    assert create_kwargs["num_partitions"] == 64


def test_milvus_delete_filter_includes_user_id() -> None:
    client = MagicMock()
    client.has_collection.return_value = True
    store = MilvusChunkVectorStore(client, collection="verso_chunks", num_partitions=64)
    user_id = uuid.uuid4()
    document_id = uuid.uuid4()
    store.delete_document(user_id=user_id, document_id=document_id)
    assert client.delete.call_args.kwargs["filter"] == (
        f'user_id == "{user_id}" and document_id == "{document_id}"'
    )
