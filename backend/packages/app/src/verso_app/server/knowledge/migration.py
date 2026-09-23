"""没有 Alembic 时的知识库兼容迁移。"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from verso_app.server.knowledge.service import KnowledgeService
from verso_framework.db.base import Base


def ensure_knowledge_schema(engine: Engine) -> None:
    """创建新表、补旧文章列，并把旧文章挂到 Default 知识库。"""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    article_columns = {column["name"] for column in inspector.get_columns("user_articles")}
    if "knowledge_base_id" not in article_columns:
        column_type = engine.dialect.type_compiler.process(
            Base.metadata.tables["user_articles"].c.knowledge_base_id.type
        )
        with engine.begin() as connection:
            connection.execute(
                text(f"ALTER TABLE user_articles ADD COLUMN knowledge_base_id {column_type}")
            )
    with Session(engine, expire_on_commit=False) as session:
        KnowledgeService().backfill_default_knowledge_bases(session)
        session.commit()
    _make_article_foreign_key_non_nullable(engine)


def _make_article_foreign_key_non_nullable(engine: Engine) -> None:
    """Postgres 可原地收紧旧表；SQLite 由新建表时的 ORM 约束保证。"""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE user_articles ALTER COLUMN knowledge_base_id SET NOT NULL")
        )
        constraint_names = {
            item["name"] for item in inspect(engine).get_foreign_keys("user_articles")
        }
        if "user_articles_knowledge_base_id_fkey" not in constraint_names:
            connection.execute(
                text(
                    "ALTER TABLE user_articles ADD CONSTRAINT "
                    "user_articles_knowledge_base_id_fkey "
                    "FOREIGN KEY (knowledge_base_id) REFERENCES knowledge_bases(id)"
                )
            )
