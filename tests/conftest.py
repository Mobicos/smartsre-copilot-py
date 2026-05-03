from __future__ import annotations

import os
import subprocess
import uuid

import psycopg
import pytest
from sqlalchemy import text
from sqlmodel import SQLModel

from app.config import config
from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import REQUIRED_TABLES
from app.security.auth import load_api_key_roles

_BASE_DSN_TEMPLATE = "postgresql://smartsre:smartsre@{host}:5432/postgres"
_TEST_DSN_TEMPLATE = "postgresql://smartsre:smartsre@{host}:5432/{db}"
_PG_CONTAINER_NAMES = (
    "smartsre-local-postgres",
    "smartsre-postgres",
    "smartsre-dev-postgres",
)
_TEST_DB_NAME = f"smartsre_test_{uuid.uuid4().hex[:8]}"


def _get_container_host() -> str:
    """Get the container's IP via docker inspect (works when localhost port forwarding is broken)."""
    configured_host = os.getenv("SMARTSRE_TEST_POSTGRES_HOST")
    if configured_host:
        return configured_host

    for container_name in _PG_CONTAINER_NAMES:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        host = result.stdout.strip()
        if result.returncode == 0 and host:
            return host

    joined_names = ", ".join(_PG_CONTAINER_NAMES)
    raise RuntimeError(
        "Unable to resolve PostgreSQL test host. Set SMARTSRE_TEST_POSTGRES_HOST "
        f"or start one of these containers: {joined_names}."
    )


@pytest.fixture(scope="session", autouse=True)
def _pg_host():
    """Resolve the PostgreSQL container host."""
    return _get_container_host()


@pytest.fixture(scope="session", autouse=True)
def _create_test_database(_pg_host: str):
    """Create a dedicated test database for the session."""
    base_dsn = _BASE_DSN_TEMPLATE.format(host=_pg_host)
    conn = psycopg.connect(base_dsn, autocommit=True)
    conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}"')
    conn.close()

    yield

    conn = psycopg.connect(base_dsn, autocommit=True)
    conn.execute(
        """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = %s AND pid != pg_backend_pid()
        """,
        (_TEST_DB_NAME,),
    )
    conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DB_NAME}"')
    conn.close()


@pytest.fixture(autouse=True)
def isolated_postgres_database(_create_test_database: None, _pg_host: str):
    """Provide a clean PostgreSQL database for each test."""
    original_dsn = config.postgres_dsn

    test_dsn = _TEST_DSN_TEMPLATE.format(host=_pg_host, db=_TEST_DB_NAME)
    config.postgres_dsn = test_dsn

    # Reset engine so it gets recreated with the test DSN
    import app.platform.persistence.database as db_module

    old_engine = db_module._engine
    db_module._engine = None
    db_module._SessionLocal = None

    SQLModel.metadata.create_all(get_engine())

    yield

    # Truncate all tables
    engine = get_engine()
    with engine.begin() as connection:
        tables = ", ".join(REQUIRED_TABLES)
        connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))

    # Restore original config
    config.postgres_dsn = original_dsn
    db_module._engine = old_engine
    db_module._SessionLocal = None
    load_api_key_roles.cache_clear()


@pytest.fixture(autouse=True)
def default_retry_policy():
    """Restore default retry configuration."""
    original = config.indexing_task_max_retries
    config.indexing_task_max_retries = 3
    yield
    config.indexing_task_max_retries = original
