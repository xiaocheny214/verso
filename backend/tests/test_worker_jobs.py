import uuid

import pytest

from verso_app.worker.jobs.knowledge import consume_knowledge_process
from verso_app.worker.jobs.loop import handle_job
from verso_app.worker.jobs.portrait import consume_portrait_sync
from verso_common.enums import BizCode
from verso_common.exceptions import BizException
from verso_common.ids import Snowflake
from verso_framework.mq import new_knowledge_process_event, new_portrait_sync_event
from verso_framework.mq.event import DeliveryEvent, JobEventType


def test_handle_job_routes_portrait(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(
        "verso_app.worker.jobs.loop.consume_portrait_sync",
        lambda event: seen.append(event.event_id),
    )
    event = new_portrait_sync_event(Snowflake(1), user_id="user-1")
    handle_job(event)
    assert seen == [event.event_id]


def test_handle_job_routes_knowledge(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[JobEventType] = []
    monkeypatch.setattr(
        "verso_app.worker.jobs.loop.consume_knowledge_process",
        lambda event: seen.append(event.event_type),
    )
    event = new_knowledge_process_event(
        Snowflake(1),
        user_id=str(uuid.uuid4()),
        knowledge_base_id=str(uuid.uuid4()),
        document_id=str(uuid.uuid4()),
        run_id=str(uuid.uuid4()),
    )
    handle_job(event)
    assert seen == [JobEventType.KNOWLEDGE_DOCUMENT_PROCESS]


def test_portrait_expired_grant_does_not_reraise(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_user_id: str) -> None:
        raise BizException("授权已过期", code=BizCode.UNAUTHORIZED)

    monkeypatch.setattr("verso_app.worker.jobs.portrait.sync_portrait", fail)
    consume_portrait_sync(new_portrait_sync_event(Snowflake(1), user_id="user-1"))


def test_portrait_retryable_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_user_id: str) -> None:
        raise BizException("画像同步失败", code=BizCode.INTERNAL_ERROR)

    monkeypatch.setattr("verso_app.worker.jobs.portrait.sync_portrait", fail)
    with pytest.raises(BizException):
        consume_portrait_sync(new_portrait_sync_event(Snowflake(1), user_id="user-1"))


def test_knowledge_commits_process(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Session:
        def __init__(self) -> None:
            self.committed = False
            self.rolled_back = False

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

        def commit(self) -> None:
            self.committed = True

        def rollback(self) -> None:
            self.rolled_back = True

    session = _Session()
    calls: list[uuid.UUID] = []

    def process(_self: object, _db: object, *, user_id: uuid.UUID, **_kwargs: object) -> None:
        calls.append(user_id)

    monkeypatch.setattr(
        "verso_app.worker.jobs.knowledge.get_session_factory",
        lambda: lambda: session,
    )
    monkeypatch.setattr(
        "verso_app.worker.jobs.knowledge.KnowledgeService.process_document",
        process,
    )
    user_id = uuid.uuid4()
    consume_knowledge_process(
        new_knowledge_process_event(
            Snowflake(1),
            user_id=str(user_id),
            knowledge_base_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            run_id=str(uuid.uuid4()),
        )
    )
    assert calls == [user_id]
    assert session.committed is True
    assert session.rolled_back is False


def test_unknown_event_is_rejected() -> None:
    event = DeliveryEvent.model_construct(
        event_id="1",
        event_type="unknown.job",
        schema_version=1,
        payload=None,
    )
    with pytest.raises(ValueError, match="未知作业"):
        handle_job(event)
