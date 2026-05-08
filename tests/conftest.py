from __future__ import annotations

# ruff: noqa: E402,I001

import os
import subprocess
import time
import uuid

from app.platform.compat import stabilize_windows_platform_detection

stabilize_windows_platform_detection()

import psycopg
import pytest
from alembic.config import Config as AlembicConfig
from psycopg import OperationalError
from sqlalchemy import text

from alembic import command
from app.config import config
from app.platform.persistence.database import get_engine
from app.platform.persistence.database import reset_for_testing
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
_PG_CONNECT_TIMEOUT_SECONDS = 30.0
_PG_HOST_PROBE_TIMEOUT_SECONDS = 4.0
_PG_CONNECT_RETRY_SECONDS = 0.5


def _postgres_host_candidates() -> list[str]:
    """Return PostgreSQL hosts in the order most reliable for local tests."""
    candidates: list[str] = []
    configured_hosts = [
        item.strip()
        for item in os.getenv("SMARTSRE_TEST_POSTGRES_HOST", "").split(",")
        if item.strip()
    ]
    candidates.extend(configured_hosts)

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
            candidates.append(host)

    candidates.extend(["localhost", "127.0.0.1"])
    candidates.extend(_PG_CONTAINER_NAMES)
    return list(dict.fromkeys(candidates))


def _connect_postgres_with_retry(
    dsn: str,
    *,
    timeout_seconds: float = _PG_CONNECT_TIMEOUT_SECONDS,
) -> psycopg.Connection:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            connect_timeout = max(min(int(timeout_seconds), 3), 1)
            return psycopg.connect(dsn, autocommit=True, connect_timeout=connect_timeout)
        except OperationalError as exc:
            last_error = exc
            time.sleep(_PG_CONNECT_RETRY_SECONDS)
    raise RuntimeError(f"PostgreSQL test database is not ready: {last_error}") from last_error


def _get_postgres_host() -> str:
    """Resolve a reachable PostgreSQL host for Docker Desktop, Compose, or CI."""
    diagnostics: list[str] = []
    for host in _postgres_host_candidates():
        base_dsn = _BASE_DSN_TEMPLATE.format(host=host)
        try:
            conn = _connect_postgres_with_retry(
                base_dsn,
                timeout_seconds=_PG_HOST_PROBE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            diagnostics.append(f"{host}: {type(exc).__name__}: {exc}")
            continue
        conn.close()
        return host

    joined_names = ", ".join(_PG_CONTAINER_NAMES)
    raise RuntimeError(
        "Unable to connect to PostgreSQL for tests. Set SMARTSRE_TEST_POSTGRES_HOST, "
        f"publish Postgres on localhost:5432, or start one of these containers: {joined_names}. "
        f"Attempts: {'; '.join(diagnostics)}"
    )


def _run_alembic_migrations(database_url: str) -> None:
    alembic_config = AlembicConfig("alembic.ini")
    original_dsn = os.environ.get("POSTGRES_DSN")
    os.environ["POSTGRES_DSN"] = database_url
    try:
        command.upgrade(alembic_config, "head")
    finally:
        if original_dsn is None:
            os.environ.pop("POSTGRES_DSN", None)
        else:
            os.environ["POSTGRES_DSN"] = original_dsn


@pytest.fixture(scope="session", autouse=True)
def _pg_host():
    """Resolve the PostgreSQL container host."""
    return _get_postgres_host()


@pytest.fixture(scope="session", autouse=True)
def _create_test_database(_pg_host: str):
    """Create a dedicated test database for the session."""
    base_dsn = _BASE_DSN_TEMPLATE.format(host=_pg_host)
    conn = _connect_postgres_with_retry(base_dsn)
    conn.execute(f'CREATE DATABASE "{_TEST_DB_NAME}" TEMPLATE template0')
    conn.close()
    _run_alembic_migrations(_TEST_DSN_TEMPLATE.format(host=_pg_host, db=_TEST_DB_NAME))

    yield

    conn = _connect_postgres_with_retry(base_dsn)
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
    original_api_key = config.app_api_key
    original_api_keys_json = config.api_keys_json

    test_dsn = _TEST_DSN_TEMPLATE.format(host=_pg_host, db=_TEST_DB_NAME)
    config.postgres_dsn = test_dsn
    config.app_api_key = ""
    config.api_keys_json = ""
    load_api_key_roles.cache_clear()

    reset_for_testing()

    yield

    # Truncate all tables
    engine = get_engine()
    with engine.begin() as connection:
        tables = ", ".join(REQUIRED_TABLES)
        connection.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))

    # Restore original config
    config.postgres_dsn = original_dsn
    config.app_api_key = original_api_key
    config.api_keys_json = original_api_keys_json
    reset_for_testing()
    load_api_key_roles.cache_clear()


@pytest.fixture(autouse=True)
def default_retry_policy():
    """Restore default retry configuration."""
    original = config.indexing_task_max_retries
    config.indexing_task_max_retries = 3
    yield
    config.indexing_task_max_retries = original
