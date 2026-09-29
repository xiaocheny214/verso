import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from tests.test_match import FakeExchange, JudgingCompatibility, _user
from verso_app.server.auth.models import User
from verso_app.server.knowledge.models import KnowledgeBase, KnowledgeDocument
from verso_app.server.knowledge.vector_store import (
    ChunkVectorPoint,
    MemoryChunkVectorStore,
)
from verso_app.server.match.compatibility import (
    TagOnlyCompatibilityEvaluator,
)
from verso_app.server.match.models import MatchCandidate, MatchCondition, MatchEvaluation
from verso_app.server.match.service import MatchService
from verso_common.enums import (
    DocumentStatus,
    MatchConditionStatus,
    MatchEvaluationOutcome,
    StrengthTag,
)
from verso_framework.config.app import AppSettings
from verso_framework.db.base import Base
from verso_framework.embed.hashing import HashingEmbedder


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


def _add_ready_chunk(
    db: Session,
    vector_store: MemoryChunkVectorStore,
    embedder: HashingEmbedder,
    *,
    user: User,
    title: str,
    text: str,
) -> tuple[KnowledgeDocument, ChunkVectorPoint]:
    kb = KnowledgeBase(
        user_id=user.id,
        name=f"kb_{user.display_name}",
        embedding_model="hashing",
        collection_name=f"col_{user.display_name}",
    )
    db.add(kb)
    db.flush()

    doc = KnowledgeDocument(
        knowledge_base_id=kb.id,
        title=title,
        status=DocumentStatus.SUCCESS,
        object_key=f"obj_{uuid.uuid4()}",
        content_type="markdown",
        source_type="article",
        chunk_count=1,
    )
    db.add(doc)
    db.flush()

    vec = embedder.embed_query(text)
    point = ChunkVectorPoint(
        user_id=user.id,
        knowledge_base_id=kb.id,
        document_id=doc.id,
        chunk_index=0,
        char_start=0,
        char_end=len(text),
        embedding=vec,
        metadata={"title": title, "source_url": f"https://example.test/{user.display_name}"},
    )
    vector_store.ensure_collection(dimension=embedder.dimensions or 8)
    vector_store.upsert([point])
    return doc, point


def test_submitter_with_no_waiting_users_stays_waiting(db: Session) -> None:
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    cond = service.submit(alice, want_text="想学习徒手健身", want_tag=StrengthTag.FITNESS)

    assert cond.status == MatchConditionStatus.WAITING
    assert cond.peer is None
    # 提问向量被缓存
    saved = db.get(MatchCondition, uuid.UUID(cond.id))
    assert saved is not None
    assert saved.question_embedding is not None
    assert len(saved.question_embedding) == 8


def test_mutual_ready_chunks_pair_via_self_join_and_writes_candidates(db: Session) -> None:
    exchange = FakeExchange()
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    service = MatchService(
        db,
        exchange=exchange,
        embedder=embedder,
        vector_store=vector_store,
        compatibility=TagOnlyCompatibilityEvaluator(),
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])

    # Alice 有关于互联网/编程的文章，Bob 想学互联网
    _add_ready_chunk(
        db,
        vector_store,
        embedder,
        user=alice,
        title="大型互联网系统架构设计",
        text="大型互联网架构实践与高并发微服务",
    )
    # Bob 有关于健身的文章，Alice 想学健身
    _add_ready_chunk(
        db,
        vector_store,
        embedder,
        user=bob,
        title="新手徒手力量训练指南",
        text="徒手自重健身训练动作标准解析",
    )

    # Alice 提交
    alice_view = service.submit(
        alice, want_text="徒手自重健身训练动作标准解析", want_tag=StrengthTag.FITNESS
    )
    assert alice_view.status == MatchConditionStatus.WAITING

    # Bob 提交（此时 Bob 检索 Alice 切片，Alice 缓存的提问也在 Bob 切片中打分）
    bob_view = service.submit(
        bob, want_text="大型互联网架构实践与高并发微服务", want_tag=StrengthTag.INTERNET
    )
    assert bob_view.status == MatchConditionStatus.MATCHED
    assert bob_view.peer is not None
    assert bob_view.peer.name == "Alice"
    assert len(exchange.opened) == 1

    # 匹配成功后，两人的候选记录已被清理
    alice_id = uuid.UUID(alice_view.id)
    bob_id = uuid.UUID(bob_view.id)
    cands = db.scalars(
        select(MatchCandidate).where(MatchCandidate.question_id.in_([alice_id, bob_id]))
    ).all()
    assert len(cands) == 0


def test_one_way_support_does_not_pair_and_stays_waiting(db: Session) -> None:
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])

    # 只有 Bob 有健身切片，Alice 没有互联网文章（只有画像标签）
    _add_ready_chunk(
        db,
        vector_store,
        embedder,
        user=bob,
        title="徒手力量训练",
        text="徒手健身核心训练法",
    )

    alice_view = service.submit(alice, want_text="徒手健身核心训练法", want_tag=StrengthTag.FITNESS)
    assert alice_view.status == MatchConditionStatus.WAITING

    bob_view = service.submit(bob, want_text="互联网分布式存储", want_tag=StrengthTag.INTERNET)
    # 单向连通（Bob 能帮 Alice，但 Alice 无法用切片帮 Bob），不能盲目配对，保持 waiting
    assert bob_view.status == MatchConditionStatus.WAITING

    # 此时 match_candidates 中只有 Alice->Bob 单向记录
    alice_id = uuid.UUID(alice_view.id)
    bob_id = uuid.UUID(bob_view.id)
    cands = db.scalars(
        select(MatchCandidate).where(MatchCandidate.question_id.in_([alice_id, bob_id]))
    ).all()
    assert len(cands) == 1
    assert cands[0].question_id == alice_id
    assert cands[0].helper_id == bob.id


def test_cross_capability_band_blocks_pairing(db: Session) -> None:
    """普通新手 (Band 1: 62分) 与高声望作者 (Band 3: 85分) 跨阶梯时拦截"""
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
    )

    novice = _user(db, name="Novice", stable=[StrengthTag.INTERNET], score=62)
    expert = _user(db, name="Expert", stable=[StrengthTag.FITNESS], score=85)

    _add_ready_chunk(
        db, vector_store, embedder, user=novice, title="基础网络", text="基础计算机网络"
    )
    _add_ready_chunk(
        db, vector_store, embedder, user=expert, title="专家力量", text="职业运动员力量训练"
    )

    novice_view = service.submit(
        novice, want_text="职业运动员力量训练", want_tag=StrengthTag.FITNESS
    )
    expert_view = service.submit(expert, want_text="基础计算机网络", want_tag=StrengthTag.INTERNET)

    # 双方切片完美互补，但因金字塔能力阶梯跨越（62分 vs 85分，阶梯差 > 1），不能配对！
    assert expert_view.status == MatchConditionStatus.WAITING
    assert novice_view.status == MatchConditionStatus.WAITING


def test_same_or_adjacent_capability_band_allows_pairing(db: Session) -> None:
    """相邻阶梯 (Band 1: 65分 与 Band 2: 75分) 允许配对"""
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
    )

    user1 = _user(db, name="User1", stable=[StrengthTag.INTERNET], score=65)
    user2 = _user(db, name="User2", stable=[StrengthTag.FITNESS], score=75)

    _add_ready_chunk(
        db, vector_store, embedder, user=user1, title="分布式消息", text="消息队列设计与选型"
    )
    _add_ready_chunk(
        db, vector_store, embedder, user=user2, title="增肌饮食", text="增肌饮食与营养规划"
    )

    service.submit(user1, want_text="增肌饮食与营养规划", want_tag=StrengthTag.FITNESS)
    res = service.submit(user2, want_text="消息队列设计与选型", want_tag=StrengthTag.INTERNET)

    assert res.status == MatchConditionStatus.MATCHED
    assert res.peer is not None
    assert res.peer.name == "User1"


def test_candidate_cleanup_on_cancel_and_expire(db: Session) -> None:
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])

    _add_ready_chunk(db, vector_store, embedder, user=bob, title="健身", text="健身指南")

    # Bob 先提交处于 waiting
    bob_view = service.submit(bob, want_text="网络协议", want_tag=StrengthTag.INTERNET)
    assert bob_view.status == MatchConditionStatus.WAITING

    # Alice 提交，命中 Bob 切片产生候选，但 Alice 无切片所以无法配对
    alice_view = service.submit(alice, want_text="健身指南", want_tag=StrengthTag.FITNESS)
    alice_id = uuid.UUID(alice_view.id)

    # 存在单向候选 (Alice -> Bob)
    cands = db.scalars(select(MatchCandidate).where(MatchCandidate.question_id == alice_id)).all()
    assert len(cands) == 1
    assert cands[0].helper_id == bob.id

    # Alice 取消匹配，候选表被清空
    service.cancel(alice)
    cands_after = db.scalars(
        select(MatchCandidate).where(MatchCandidate.question_id == alice_id)
    ).all()
    assert len(cands_after) == 0


def test_title_fallback_when_enabled_and_no_ready_bodies(db: Session) -> None:
    """当开启 match_title_fallback_when_no_ready 且池中所有人均无 ready 文档时，可回退到画像标题匹配"""
    settings = AppSettings(match_title_fallback_when_no_ready=True)
    vector_store = MemoryChunkVectorStore()
    embedder = HashingEmbedder(dims=8)
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
        settings=settings,
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])

    # 双方均无切片文章，但画像标签互补
    service.submit(alice, want_text="想学健身动作", want_tag=StrengthTag.FITNESS)
    res = service.submit(bob, want_text="想学互联网产品", want_tag=StrengthTag.INTERNET)

    # 成功回退并配对
    assert res.status == MatchConditionStatus.MATCHED
    assert res.peer is not None
    assert res.peer.name == "Alice"


def test_no_title_fallback_by_default_when_no_ready_bodies(db: Session) -> None:
    """默认 match_title_fallback_when_no_ready=False，无人拥有 ready 文档时保持 waiting"""
    settings = AppSettings(match_title_fallback_when_no_ready=False)
    vector_store = MemoryChunkVectorStore()
    embedder = HashingEmbedder(dims=8)
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
        settings=settings,
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])

    # 双方均无切片文章
    service.submit(alice, want_text="想学健身动作", want_tag=StrengthTag.FITNESS)
    res = service.submit(bob, want_text="想学互联网产品", want_tag=StrengthTag.INTERNET)

    # 默认不允许回退，保持 waiting
    assert res.status == MatchConditionStatus.WAITING


def test_evaluation_records_chunk_evidence_id(db: Session) -> None:
    """验证录入的决策记录能够体现 article:...:c{n} 证据 ID"""
    embedder = HashingEmbedder(dims=8)
    vector_store = MemoryChunkVectorStore()
    compatibility = JudgingCompatibility(allowed=True)
    service = MatchService(
        db,
        embedder=embedder,
        vector_store=vector_store,
        compatibility=compatibility,
    )

    alice = _user(db, name="Alice", stable=[StrengthTag.INTERNET])
    bob = _user(db, name="Bob", stable=[StrengthTag.FITNESS])

    _add_ready_chunk(db, vector_store, embedder, user=alice, title="Python", text="Python并发")
    _add_ready_chunk(db, vector_store, embedder, user=bob, title="Running", text="马拉松备赛")

    service.submit(alice, want_text="马拉松备赛", want_tag=StrengthTag.FITNESS)
    res = service.submit(bob, want_text="Python并发", want_tag=StrengthTag.INTERNET)
    assert res.status == MatchConditionStatus.MATCHED

    # 检查 MatchEvaluation 中的 evidence 是否包含 article:...
    eval_row = db.scalar(select(MatchEvaluation))
    assert eval_row is not None
    assert eval_row.outcome == MatchEvaluationOutcome.PAIRED.value
    # 双方的 candidate_evidence 首项均为切片证据
    assert len(compatibility.calls) == 1
    dir1, dir2 = compatibility.calls[0]
    assert dir1.candidate_evidence[0].id.startswith("article:")
    assert dir2.candidate_evidence[0].id.startswith("article:")
