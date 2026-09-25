from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from verso_app.bootstrap.app import create_app
from verso_app.server.auth.models import User
from verso_app.server.collect.models import ArticleCollectionRecord
from verso_app.server.collect.service import CollectService
from verso_app.server.knowledge.models import KnowledgeBase
from verso_app.server.knowledge.service import KnowledgeService
from verso_app.server.knowledge.vector_store import MemoryChunkVectorStore
from verso_app.web.middleware.auth import get_current_user, get_session
from verso_common.enums import BizCode, UserStatus
from verso_common.exceptions import BizException
from verso_framework.db.base import Base
from verso_framework.db.migrations import run_pending_migrations
from verso_framework.embed import HashingEmbedder
from verso_framework.storage import MemoryObjectStore


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session


def _user(db: Session, token: str = "token-a") -> User:
    user = User(
        zhihu_url_token=token,
        display_name=token,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    db.flush()
    return user


def test_knowledge_base_crud_is_scoped_to_owner(db: Session) -> None:
    service = KnowledgeService()
    owner = _user(db)
    outsider = _user(db, token="token-b")

    created = service.create(db, user_id=owner.id, name="Writing")
    assert created.name == "Writing"
    assert created.embedding_model == ""
    assert created.collection_name == "writing"
    assert service.list(db, user_id=owner.id) == [created]

    updated = service.update(db, user_id=owner.id, knowledge_base_id=created.id, name="Notes")
    assert updated.name == "Notes"

    with pytest.raises(BizException) as exc:
        service.get(db, user_id=outsider.id, knowledge_base_id=created.id)
    assert exc.value.code == BizCode.NOT_FOUND

    service.delete(db, user_id=owner.id, knowledge_base_id=created.id)
    assert service.list(db, user_id=owner.id) == []


def test_knowledge_base_accepts_owner_collection_name(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)

    created = service.create(db, user_id=user.id, name="Essays", collection_name="My_Notes")
    assert created.collection_name == "my_notes"
    assert created.embedding_model == ""

    default_base = service.get_or_create_default(db, user_id=user.id)
    assert default_base.collection_name == "default"

    updated = service.update(
        db,
        user_id=user.id,
        knowledge_base_id=created.id,
        collection_name="essays_v2",
    )
    assert updated.collection_name == "essays_v2"


def test_knowledge_base_rejects_duplicate_or_invalid_collection_name(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)
    service.create(db, user_id=user.id, name="Writing", collection_name="notes")

    with pytest.raises(BizException) as duplicate:
        service.create(db, user_id=user.id, name="Other", collection_name="notes")
    assert duplicate.value.code == BizCode.CONFLICT

    with pytest.raises(BizException) as invalid:
        service.create(db, user_id=user.id, name="Bad", collection_name="1notes")
    assert invalid.value.code == BizCode.BAD_REQUEST


def test_knowledge_routes_store_collection_name_and_ignore_embedding(db: Session) -> None:
    owner = _user(db)
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)

    created = client.post(
        "/me/knowledge-bases",
        json={
            "name": "Writing",
            "collection_name": "essays",
            "embedding_model": "other-embed",
        },
    )
    assert created.json()["code"] == BizCode.SUCCESS
    assert created.json()["data"]["collection_name"] == "essays"
    assert created.json()["data"]["embedding_model"] == ""
    knowledge_base_id = created.json()["data"]["id"]

    patched = client.patch(
        f"/me/knowledge-bases/{knowledge_base_id}",
        json={"collection_name": "drafts", "embedding_model": "still-ignored"},
    )
    assert patched.json()["code"] == BizCode.SUCCESS
    assert patched.json()["data"]["collection_name"] == "drafts"
    assert patched.json()["data"]["embedding_model"] == ""

    app.dependency_overrides.clear()


def test_knowledge_base_delete_ignores_collection_records(db: Session) -> None:
    service = KnowledgeService()
    archive = CollectService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)
    knowledge_base = service.create(db, user_id=user.id, name="Writing")

    archive.put_markdown(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/1",
        data=b"# article",
        content_type="article",
    )

    service.delete(db, user_id=user.id, knowledge_base_id=knowledge_base.id)
    assert db.get(KnowledgeBase, knowledge_base.id) is None


def test_knowledge_document_crud_from_collect(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    service = KnowledgeService.with_deps(store, vectors=vectors)
    archive = CollectService(store, key_prefix="articles")
    owner = _user(db)
    outsider = _user(db, token="token-b")
    base_a = service.create(db, user_id=owner.id, name="Writing")
    base_b = service.create(db, user_id=owner.id, name="Drafts")
    url = "https://zhuanlan.zhihu.com/p/doc-1"

    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"# body",
        content_type="article",
        title="Doc One",
    )

    attached = service.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base_a.id,
        source_url=url,
        collect=archive,
    )
    assert attached.status == "pending"
    assert attached.chunk_count == 0
    assert attached.source_type == "zhihu"
    assert attached.title == "Doc One"
    assert attached.content_type == "markdown"

    again = service.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base_a.id,
        source_url=url,
        collect=archive,
    )
    assert again.id == attached.id

    assert [
        row.id for row in service.list_documents(db, user_id=owner.id, knowledge_base_id=base_a.id)
    ] == [attached.id]
    assert service.list_documents(db, user_id=owner.id, knowledge_base_id=base_b.id) == []

    with pytest.raises(BizException) as not_ready:
        service.attach_from_collect(
            db,
            user_id=owner.id,
            knowledge_base_id=base_a.id,
            source_url="https://zhuanlan.zhihu.com/p/missing",
            collect=archive,
        )
    assert not_ready.value.code == BizCode.BAD_REQUEST

    patched = service.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base_a.id,
        document_id=attached.id,
        title="Renamed",
        enabled=False,
        process_mode="none",
    )
    assert patched.title == "Renamed"
    assert patched.enabled is False
    assert patched.process_mode == "none"
    assert patched.status == "pending"

    with pytest.raises(BizException) as hidden:
        service.get_document(
            db,
            user_id=outsider.id,
            knowledge_base_id=base_a.id,
            document_id=attached.id,
        )
    assert hidden.value.code == BizCode.NOT_FOUND

    with pytest.raises(BizException) as refuse:
        service.delete(db, user_id=owner.id, knowledge_base_id=base_a.id)
    assert refuse.value.code == BizCode.CONFLICT
    assert db.get(KnowledgeBase, base_a.id) is not None

    service.delete_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base_a.id,
        document_id=attached.id,
    )
    assert service.list_documents(db, user_id=owner.id, knowledge_base_id=base_a.id) == []
    # collect 正文仍在对象存储（共享 object_key，删文档不删 Kodo）
    assert store.get(attached.object_key) == b"# body"
    service.delete(db, user_id=owner.id, knowledge_base_id=base_a.id)
    assert db.get(KnowledgeBase, base_a.id) is None


def test_knowledge_document_routes(db: Session) -> None:
    owner = _user(db)
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(store, vectors=vectors)
    url = "https://zhuanlan.zhihu.com/p/route-1"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"route body",
        content_type="article",
        title="Route Doc",
    )

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    from verso_app.web.middleware.auth import get_collect_service

    app.dependency_overrides[get_collect_service] = lambda: archive
    app.dependency_overrides[KnowledgeService] = lambda: knowledge
    client = TestClient(app)

    created = client.post("/me/knowledge-bases", json={"name": "Writing"})
    knowledge_base_id = created.json()["data"]["id"]

    attached = client.post(
        f"/me/knowledge-bases/{knowledge_base_id}/documents/from-collect",
        json={"source_url": url},
    )
    assert attached.json()["code"] == BizCode.SUCCESS
    document_id = attached.json()["data"]["id"]
    assert attached.json()["data"]["status"] == "pending"
    assert attached.json()["data"]["source_url"] == url
    assert attached.json()["data"]["chunk_strategy"] == "fixed_size"

    listed = client.get(f"/me/knowledge-bases/{knowledge_base_id}/documents")
    assert [item["id"] for item in listed.json()["data"]] == [document_id]

    legacy_list = client.get(f"/me/knowledge-bases/{knowledge_base_id}/articles")
    assert [item["id"] for item in legacy_list.json()["data"]] == [document_id]
    assert "source_type" in legacy_list.json()["data"][0]

    patched = client.patch(
        f"/me/knowledge-bases/{knowledge_base_id}/documents/{document_id}",
        json={"title": "Patched", "chunk_size": 500},
    )
    assert patched.json()["code"] == BizCode.SUCCESS
    assert patched.json()["data"]["title"] == "Patched"
    assert patched.json()["data"]["chunk_size"] == 500

    deleted = client.delete(f"/me/knowledge-bases/{knowledge_base_id}/documents/{document_id}")
    assert deleted.json()["code"] == BizCode.SUCCESS
    assert client.get(f"/me/knowledge-bases/{knowledge_base_id}/documents").json()["data"] == []

    app.dependency_overrides.clear()


def test_knowledge_document_chunk_preview(db: Session) -> None:
    store = MemoryObjectStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(store)
    owner = _user(db)
    outsider = _user(db, token="token-b")
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/preview-1"
    body = b"# Hello\n\n" + b"abcdefghi\n\n" + b"xyz"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=body,
        content_type="article",
        title="Preview",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )

    _row, preview = knowledge.preview_chunks(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_strategy="fixed_size",
        chunk_size=8,
        overlap=0,
    )
    assert preview.strategy.value == "fixed_size"
    assert preview.chunks
    assert all(chunk.text for chunk in preview.chunks)

    structure = knowledge.preview_chunks(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_strategy="structure_aware",
        chunk_size=40,
        overlap=0,
    )[1]
    assert structure.strategy.value == "structure_aware"
    assert structure.chunks[0].text.startswith("# Hello")

    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        process_mode="none",
    )
    empty = knowledge.preview_chunks(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )[1]
    assert empty.chunks == ()

    with pytest.raises(BizException) as hidden:
        knowledge.preview_chunks(
            db,
            user_id=outsider.id,
            knowledge_base_id=base.id,
            document_id=doc.id,
        )
    assert hidden.value.code == BizCode.NOT_FOUND

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[KnowledgeService] = lambda: knowledge
    client = TestClient(app)
    response = client.post(
        f"/me/knowledge-bases/{base.id}/documents/{doc.id}/chunk-preview",
        json={"chunk_strategy": "fixed_size", "chunk_size": 10, "overlap": 0},
    )
    # process_mode still none from earlier
    assert response.json()["code"] == BizCode.SUCCESS
    assert response.json()["data"]["chunks"] == []

    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        process_mode="chunk",
    )
    live = client.post(
        f"/me/knowledge-bases/{base.id}/documents/{doc.id}/chunk-preview",
        json={"chunk_strategy": "fixed_size", "chunk_size": 10, "overlap": 0},
    )
    assert live.json()["code"] == BizCode.SUCCESS
    assert live.json()["data"]["document_id"] == str(doc.id)
    assert live.json()["data"]["chunks"]
    assert "text" in live.json()["data"]["chunks"][0]
    app.dependency_overrides.clear()


def test_knowledge_document_process_writes_vectors_without_text(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(
        store,
        embedder=HashingEmbedder(dims=4),
        vectors=vectors,
    )
    owner = _user(db)
    outsider = _user(db, token="token-b")
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/process-1"
    body = b"abcdefghij"  # 10 chars → 2 chunks at size 5 overlap 0
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=body,
        content_type="article",
        title="Process Me",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )
    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_strategy="fixed_size",
        chunk_size=5,
        overlap=0,
    )

    document, run = knowledge.process_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert document.status == "success"
    assert document.chunk_count == 2
    assert run.status == "success"
    assert run.chunk_count == 2
    assert vectors.list_document_ids(document_id=doc.id) == [
        f"{doc.id}:0",
        f"{doc.id}:1",
    ]
    point = vectors._points[f"{doc.id}:0"]
    assert point.char_start == 0
    assert point.char_end == 5
    assert len(point.embedding) == 4
    assert not hasattr(point, "text")

    # re-process replaces vectors
    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_size=10,
        overlap=0,
    )
    document2, run2 = knowledge.process_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert document2.chunk_count == 1
    assert run2.chunk_count == 1
    assert vectors.list_document_ids(document_id=doc.id) == [f"{doc.id}:0"]

    runs = knowledge.list_process_runs(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert {item.id for item in runs} == {run.id, run2.id}
    assert any(item.chunk_count == 1 for item in runs)
    assert any(item.chunk_count == 2 for item in runs)

    with pytest.raises(BizException) as hidden:
        knowledge.process_document(
            db,
            user_id=outsider.id,
            knowledge_base_id=base.id,
            document_id=doc.id,
        )
    assert hidden.value.code == BizCode.NOT_FOUND


def test_knowledge_document_process_mode_none_clears_vectors(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(
        store,
        embedder=HashingEmbedder(dims=4),
        vectors=vectors,
    )
    owner = _user(db)
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/process-none"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"hello world",
        content_type="article",
        title="None Mode",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )
    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_size=5,
        overlap=0,
    )
    knowledge.process_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert vectors.list_document_ids(document_id=doc.id)

    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        process_mode="none",
    )
    document, run = knowledge.process_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert document.status == "success"
    assert document.chunk_count == 0
    assert run.status == "success"
    assert run.chunk_count == 0
    assert vectors.list_document_ids(document_id=doc.id) == []


def test_knowledge_document_delete_clears_vectors_keeps_object(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(
        store,
        embedder=HashingEmbedder(dims=4),
        vectors=vectors,
    )
    owner = _user(db)
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/process-delete"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"delete me please",
        content_type="article",
        title="Delete",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )
    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_size=8,
        overlap=0,
    )
    knowledge.process_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert vectors.list_document_ids(document_id=doc.id)
    object_key = doc.object_key

    knowledge.delete_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert vectors.list_document_ids(document_id=doc.id) == []
    assert store.get(object_key) == b"delete me please"
    assert knowledge.list_documents(db, user_id=owner.id, knowledge_base_id=base.id) == []


def test_knowledge_reattach_changed_body_clears_vectors(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(
        store,
        embedder=HashingEmbedder(dims=4),
        vectors=vectors,
    )
    owner = _user(db)
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/process-reattach"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"first body text",
        content_type="article",
        title="V1",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )
    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_size=8,
        overlap=0,
    )
    knowledge.process_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert vectors.list_document_ids(document_id=doc.id)

    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"second body text changed",
        content_type="article",
        title="V2",
    )
    updated = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )
    assert updated.id == doc.id
    assert updated.status == "pending"
    assert updated.chunk_count == 0
    assert updated.title == "V2"
    assert vectors.list_document_ids(document_id=doc.id) == []


def test_knowledge_document_delete_refuses_when_vector_cleanup_fails(db: Session) -> None:
    store = MemoryObjectStore()

    class BoomVectors(MemoryChunkVectorStore):
        def delete_document(self, *, document_id: uuid.UUID) -> None:
            raise RuntimeError("milvus down")

    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(store, vectors=BoomVectors())
    owner = _user(db)
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/process-delete-fail"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"keep me",
        content_type="article",
        title="Keep",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )

    with pytest.raises(BizException) as failed:
        knowledge.delete_document(
            db,
            user_id=owner.id,
            knowledge_base_id=base.id,
            document_id=doc.id,
        )
    assert failed.value.code == BizCode.INTERNAL_ERROR
    assert (
        knowledge.get_document(
            db,
            user_id=owner.id,
            knowledge_base_id=base.id,
            document_id=doc.id,
        ).id
        == doc.id
    )


def test_knowledge_document_process_marks_failed_on_embed_error(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()

    class BoomEmbedder:
        dimensions = 4

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embed boom")

        def embed_query(self, text: str) -> list[float]:
            raise RuntimeError("embed boom")

    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(
        store,
        embedder=BoomEmbedder(),
        vectors=vectors,
    )
    owner = _user(db)
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    url = "https://zhuanlan.zhihu.com/p/process-fail"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"fail body",
        content_type="article",
        title="Fail",
    )
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )

    with pytest.raises(BizException) as failed:
        knowledge.process_document(
            db,
            user_id=owner.id,
            knowledge_base_id=base.id,
            document_id=doc.id,
        )
    assert failed.value.code == BizCode.INTERNAL_ERROR

    refreshed = knowledge.get_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert refreshed.status == "failed"
    assert refreshed.error_class == "RuntimeError"
    runs = knowledge.list_process_runs(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
    )
    assert len(runs) == 1
    assert runs[0].status == "failed"
    assert runs[0].error_class == "RuntimeError"
    assert vectors.list_document_ids(document_id=doc.id) == []


def test_knowledge_document_process_routes(db: Session) -> None:
    store = MemoryObjectStore()
    vectors = MemoryChunkVectorStore()
    archive = CollectService(store, key_prefix="articles")
    knowledge = KnowledgeService.with_deps(
        store,
        embedder=HashingEmbedder(dims=4),
        vectors=vectors,
    )
    owner = _user(db)
    url = "https://zhuanlan.zhihu.com/p/process-route"
    archive.put_markdown(
        db,
        user_id=owner.id,
        source_url=url,
        data=b"route process body",
        content_type="article",
        title="Route Process",
    )
    base = knowledge.create(db, user_id=owner.id, name="Writing")
    doc = knowledge.attach_from_collect(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        source_url=url,
        collect=archive,
    )
    knowledge.update_document(
        db,
        user_id=owner.id,
        knowledge_base_id=base.id,
        document_id=doc.id,
        chunk_size=8,
        overlap=0,
    )

    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[KnowledgeService] = lambda: knowledge
    client = TestClient(app)

    processed = client.post(
        f"/me/knowledge-bases/{base.id}/documents/{doc.id}/process",
    )
    assert processed.json()["code"] == BizCode.SUCCESS
    assert processed.json()["data"]["document"]["status"] == "success"
    assert processed.json()["data"]["document"]["chunk_count"] >= 1
    assert processed.json()["data"]["run"]["status"] == "success"
    assert "text" not in processed.json()["data"]["run"]

    listed = client.get(
        f"/me/knowledge-bases/{base.id}/documents/{doc.id}/process-runs",
    )
    assert listed.json()["code"] == BizCode.SUCCESS
    assert len(listed.json()["data"]) == 1
    assert listed.json()["data"][0]["id"] == processed.json()["data"]["run"]["id"]
    app.dependency_overrides.clear()


def test_collection_record_does_not_require_knowledge_base(db: Session) -> None:
    archive = CollectService(MemoryObjectStore(), key_prefix="articles")
    user = _user(db)

    row = archive.put_markdown(
        db,
        user_id=user.id,
        source_url="https://zhuanlan.zhihu.com/p/default",
        data=b"default",
        content_type="article",
        summary="a zhihu piece",
    )

    assert row.description == "a zhihu piece"
    assert not hasattr(row, "knowledge_base_id")
    assert [item.source_url for item in archive.list_by_user(db, user_id=user.id)] == [
        "https://zhuanlan.zhihu.com/p/default"
    ]


def test_user_without_articles_has_no_default_base(db: Session) -> None:
    service = KnowledgeService()
    user = _user(db)

    assert service.list(db, user_id=user.id) == []


def test_knowledge_routes_return_owner_scoped_data(db: Session) -> None:
    owner = _user(db)
    outsider = _user(db, token="token-b")
    app = create_app()
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)

    created = client.post("/me/knowledge-bases", json={"name": "Writing"})
    assert created.json()["code"] == BizCode.SUCCESS
    knowledge_base_id = created.json()["data"]["id"]
    assert created.json()["data"]["collection_name"] == "writing"
    assert created.json()["data"]["embedding_model"] == ""

    listed = client.get("/me/knowledge-bases")
    assert [item["name"] for item in listed.json()["data"]] == ["Writing"]

    app.dependency_overrides[get_current_user] = lambda: outsider
    hidden = client.get(f"/me/knowledge-bases/{knowledge_base_id}")
    assert hidden.json()["code"] == BizCode.NOT_FOUND

    app.dependency_overrides.clear()


def test_legacy_user_articles_rename_to_collection_records(db: Session) -> None:
    user = _user(db)
    engine = db.get_bind()
    db.commit()
    Base.metadata.drop_all(engine, tables=[ArticleCollectionRecord.__table__])
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE user_articles (
                    id CHAR(32) PRIMARY KEY,
                    user_id CHAR(32) NOT NULL,
                    source_url TEXT NOT NULL,
                    content_type VARCHAR(32) NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    object_key TEXT NOT NULL UNIQUE,
                    content_hash VARCHAR(64),
                    byte_size INTEGER,
                    status VARCHAR(16) NOT NULL,
                    error_class VARCHAR(64),
                    fetched_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    CONSTRAINT user_articles_user_source_url UNIQUE (user_id, source_url)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO user_articles
                    (id, user_id, source_url, content_type, title, summary, object_key, status,
                     created_at, updated_at)
                VALUES
                    (:id, :user_id, :source_url, 'article', 'legacy', 'from zhihu',
                     'articles/legacy', 'pending', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """
            ),
            {
                "id": "f" * 32,
                "user_id": user.id.hex,
                "source_url": "https://zhuanlan.zhihu.com/p/legacy",
            },
        )

    run_pending_migrations(engine)
    run_pending_migrations(engine)

    row = db.get(ArticleCollectionRecord, uuid.UUID("f" * 32))
    assert row is not None
    assert row.title == "legacy"
    assert row.description == "from zhihu"
    assert row.source_url == "https://zhuanlan.zhihu.com/p/legacy"
    assert db.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one() == 1
