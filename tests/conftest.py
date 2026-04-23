from __future__ import annotations

from pathlib import Path

import pytest

from app.config import config
from app.persistence.database import database_manager
from app.security.auth import load_api_key_roles


@pytest.fixture(autouse=True)
def isolated_sqlite_database(tmp_path: Path):
    """为每个测试提供隔离的 SQLite 数据库。"""
    original_backend = database_manager.backend
    original_path = database_manager.sqlite_path
    original_dsn = database_manager.postgres_dsn
    original_initialized = database_manager._initialized

    database_manager.backend = "sqlite"
    database_manager.sqlite_path = tmp_path / "test.db"
    database_manager.postgres_dsn = ""
    database_manager._initialized = False
    database_manager.initialize()

    yield

    database_manager.backend = original_backend
    database_manager.sqlite_path = original_path
    database_manager.postgres_dsn = original_dsn
    database_manager._initialized = original_initialized
    load_api_key_roles.cache_clear()


@pytest.fixture(autouse=True)
def default_retry_policy():
    """恢复默认重试配置。"""
    original = config.indexing_task_max_retries
    config.indexing_task_max_retries = 3
    yield
    config.indexing_task_max_retries = original
