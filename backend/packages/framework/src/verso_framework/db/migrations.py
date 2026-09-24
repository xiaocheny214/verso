"""Versioned SQL migration runner."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, text


def run_pending_migrations(
    engine: Engine,
    migrations_dir: Path | None = None,
    *,
    baseline: bool = False,
) -> None:
    """Apply ordered SQL migrations once and record their versions."""
    directory = migrations_dir or _default_migrations_dir()
    suffix = f".{engine.dialect.name}.sql"
    files = sorted(directory.glob(f"*{suffix}"))
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version VARCHAR(255) PRIMARY KEY, "
                "applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        applied = {
            row[0]
            for row in connection.execute(text("SELECT version FROM schema_migrations")).all()
        }
    for path in files:
        version = path.name.removesuffix(suffix)
        if version in applied:
            continue
        with engine.begin() as connection:
            if not baseline:
                _execute_sql_file(connection, path, dialect=engine.dialect.name)
            connection.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:version)"),
                {"version": version},
            )


def _default_migrations_dir() -> Path:
    candidates = (
        Path.cwd() / "migration",
        Path.cwd().parent / "migration",
        Path(__file__).resolve().parents[6] / "migration",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def _execute_sql_file(connection, path: Path, *, dialect: str) -> None:
    sql = path.read_text(encoding="utf-8")
    if dialect == "sqlite":
        for statement in sql.split(";\n"):
            statement = statement.strip()
            if statement:
                connection.exec_driver_sql(statement)
        return
    connection.exec_driver_sql(sql)
