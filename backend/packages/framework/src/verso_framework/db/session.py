"""数据库 engine 与 session 工厂。

- ``get_engine`` / ``get_session_factory``：首次调用时创建（需要能读到 POSTGRES_*）
- ``get_session``：每请求一个 session，请求结束自动提交或回滚

不要把 ORM session 绑在 WebSocket 生命周期上。
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from verso_framework.config.database import DatabaseSettings


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()


@lru_cache
def get_engine() -> Engine:
    settings = get_database_settings()
    return create_engine(
        settings.url,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_pre_ping=settings.pool_pre_ping,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """每调用一次一个同步 session，结束自动关闭。"""
    factory = get_session_factory()
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
