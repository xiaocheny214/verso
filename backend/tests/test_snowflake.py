import pytest

from verso_common.ids import MAX_WORKER_ID, Snowflake, SnowflakeClockError
from verso_common.ids import snowflake as snowflake_mod


def test_ids_increase_and_stay_unique() -> None:
    gen = Snowflake(1)
    ids = [gen.next_id() for _ in range(1000)]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_worker_id_is_embedded() -> None:
    worker_id = 7
    value = Snowflake(worker_id).next_id()
    embedded = (value >> 12) & MAX_WORKER_ID
    assert embedded == worker_id


def test_worker_id_out_of_range() -> None:
    with pytest.raises(ValueError):
        Snowflake(-1)
    with pytest.raises(ValueError):
        Snowflake(MAX_WORKER_ID + 1)


def test_clock_rollback_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"ms": 1_767_225_600_000}
    monkeypatch.setattr(snowflake_mod, "_now_ms", lambda: clock["ms"])
    gen = Snowflake(1)
    gen.next_id()
    clock["ms"] -= 5
    with pytest.raises(SnowflakeClockError):
        gen.next_id()
