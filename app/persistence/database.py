"""Database management helpers for SQLite and PostgreSQL."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import DATA_DIR, config
from app.persistence.schema import REQUIRED_TABLES, SQLITE_SCHEMA_STATEMENTS

_psycopg: Any = None
_dict_row: Any = None

try:
    import psycopg as _imported_psycopg
    from psycopg.rows import dict_row as _imported_dict_row

    _psycopg = _imported_psycopg
    _dict_row = _imported_dict_row
except Exception:  # pragma: no cover - psycopg may be absent in SQLite-only environments
    pass

psycopg: Any = _psycopg
dict_row: Any = _dict_row


class DatabaseConnectionAdapter:
    """Normalize SQLite and PostgreSQL access behind a DB-API-like wrapper."""

    def __init__(self, connection: Any, backend: str) -> None:
        self._connection = connection
        self._backend = backend

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> Any:
        normalized_query = self._normalize_query(query)
        normalized_params = tuple(params or ())
        if normalized_params:
            return self._connection.execute(normalized_query, normalized_params)
        return self._connection.execute(normalized_query)

    def fetchone(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> Any:
        return self.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] | list[Any] | None = None) -> Any:
        return self.execute(query, params).fetchall()

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def _normalize_query(self, query: str) -> str:
        if self._backend == "postgres":
            return query.replace("?", "%s")
        return query


class DatabaseManager:
    """Handle database initialization and runtime connections."""

    def __init__(
        self,
        *,
        backend: str,
        sqlite_path: str,
        postgres_dsn: str,
    ) -> None:
        self.backend = backend
        self.sqlite_path = Path(sqlite_path)
        self.postgres_dsn = postgres_dsn
        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> None:
        if self._initialized:
            return

        if self.backend == "postgres":
            self._initialize_postgres()
        else:
            self._initialize_sqlite()

        self._initialized = True

    @contextmanager
    def get_connection(self) -> Iterator[DatabaseConnectionAdapter]:
        connection: Any
        if self.backend == "postgres":
            if psycopg is None:
                raise RuntimeError("PostgreSQL support requires the optional 'psycopg' dependency")
            connection = psycopg.connect(self.postgres_dsn, row_factory=dict_row)
            adapter = DatabaseConnectionAdapter(connection, backend="postgres")
        else:
            connection = sqlite3.connect(self.sqlite_path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            adapter = DatabaseConnectionAdapter(connection, backend="sqlite")

        try:
            yield adapter
            adapter.commit()
        except Exception:
            adapter.rollback()
            raise
        finally:
            adapter.close()

    def health_check(self) -> bool:
        try:
            self.initialize()
            with self.get_connection() as connection:
                row = connection.fetchone("SELECT 1 AS ok")
            if row is None:
                return False
            return bool(row["ok"] == 1)
        except Exception as exc:
            logger.error(f"Database health check failed: {exc}")
            return False

    def placeholders(self, count: int) -> str:
        return ", ".join("?" for _ in range(count))

    def _initialize_sqlite(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        with self.get_connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute("PRAGMA foreign_keys=ON;")
            for statement in SQLITE_SCHEMA_STATEMENTS:
                connection.execute(statement)
            self._ensure_sqlite_columns(
                connection,
                "indexing_tasks",
                {
                    "attempt_count": "INTEGER NOT NULL DEFAULT 0",
                    "max_retries": "INTEGER NOT NULL DEFAULT 3",
                },
            )

        logger.info(f"SQLite database initialized: {self.sqlite_path}")

    def _initialize_postgres(self) -> None:
        if psycopg is None:
            raise RuntimeError("PostgreSQL support requires the optional 'psycopg' dependency")
        if not self.postgres_dsn:
            raise RuntimeError("PostgreSQL support requires POSTGRES_DSN to be configured")

        with self.get_connection() as connection:
            rows = connection.fetchall(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            )

        existing_tables = {row["table_name"] for row in rows}
        missing_tables = [table for table in REQUIRED_TABLES if table not in existing_tables]
        if missing_tables:
            raise RuntimeError(
                "PostgreSQL schema is missing required tables. Run migrations first: "
                + ", ".join(missing_tables)
            )

        logger.info("PostgreSQL schema verified")

    def _ensure_sqlite_columns(
        self,
        connection: DatabaseConnectionAdapter,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        rows = connection.fetchall(f"PRAGMA table_info({table_name})")
        existing = {row["name"] for row in rows}
        for column_name, definition in columns.items():
            if column_name in existing:
                continue
            connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


database_manager = DatabaseManager(
    backend=config.database_backend,
    sqlite_path=config.database_path,
    postgres_dsn=config.postgres_dsn,
)
