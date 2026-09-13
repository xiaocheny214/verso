from verso_framework.db import get_engine, get_redis, get_session_factory


def test_engine_does_not_connect_on_create() -> None:
    engine = get_engine()
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.database == "verso"


def test_session_factory_is_cached() -> None:
    assert get_session_factory() is get_session_factory()


def test_redis_client_decodes_responses() -> None:
    client = get_redis()
    assert client.connection_pool.connection_kwargs["decode_responses"] is True
