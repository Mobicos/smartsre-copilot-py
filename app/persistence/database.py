"""数据库持久化基础设施。

支持 SQLite（本地开发）与 PostgreSQL（生产环境）两种后端。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from loguru import logger

from app.config import DATA_DIR, config
from app.persistence.schema import REQUIRED_TABLES, SQLITE_SCHEMA_STATEMENTS

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - 运行环境可能未安装 psycopg
    psycopg = None
    dict_row = None


class DatabaseConnectionAdapter:
    """统一 SQLite / PostgreSQL 的 DB-API 差异。"""

    def __init__(self, connection: Any, backend: str) -> None:
        self._connection = connection
        self._backend = backend

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
        normalized_query = self._normalize_query(query)
        normalized_params = tuple(params or ())
        if normalized_params:
            return self._connection.execute(normalized_query, normalized_params)
        return self._connection.execute(normalized_query)

    def fetchone(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
        return self.execute(query, params).fetchone()

    def fetchall(self, query: str, params: tuple[Any, ...] | list[Any] | None = None):
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
    """统一管理应用数据库。

    SQLite 在本地开发模式下自动引导 schema。
    PostgreSQL 要求先执行 Alembic 迁移，再在启动期做 schema 就绪检查。
    """

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
        """初始化数据库或校验 schema 就绪状态。"""
        if self._initialized:
            return

        if self.backend == "postgres":
            self._initialize_postgres()
        else:
            self._initialize_sqlite()

        self._initialized = True

    @contextmanager
    def get_connection(self) -> Iterator[DatabaseConnectionAdapter]:
        """获取连接适配器。"""
        if self.backend == "postgres":
            if psycopg is None:
                raise RuntimeError("当前配置为 PostgreSQL，但未安装 psycopg")
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
        """数据库健康检查。"""
        try:
            self.initialize()
            with self.get_connection() as connection:
                row = connection.fetchone("SELECT 1 AS ok")
            if row is None:
                return False
            return bool(row["ok"] == 1)
        except Exception as exc:
            logger.error(f"数据库健康检查失败: {exc}")
            return False

    def placeholders(self, count: int) -> str:
        """生成兼容当前数据库的占位符列表。"""
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

        logger.info(f"SQLite 数据库初始化完成: {self.sqlite_path}")

    def _initialize_postgres(self) -> None:
        if psycopg is None:
            raise RuntimeError("当前配置为 PostgreSQL，但未安装 psycopg")
        if not self.postgres_dsn:
            raise RuntimeError("当前配置为 PostgreSQL，但未设置 POSTGRES_DSN")

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
                "PostgreSQL schema 未初始化，请先执行数据库迁移。缺失表: "
                + ", ".join(missing_tables)
            )

        logger.info("PostgreSQL schema 检查通过")

    def _ensure_sqlite_columns(
        self,
        connection: DatabaseConnectionAdapter,
        table_name: str,
        columns: dict[str, str],
    ) -> None:
        """为 SQLite 已存在表补充缺失列。"""
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
