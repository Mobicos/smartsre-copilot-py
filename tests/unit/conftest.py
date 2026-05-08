"""Unit test conftest — overrides the autouse DB fixture from tests/conftest.py."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_postgres_database():
    """No-op override: unit tests do not need a live database."""
    yield


@pytest.fixture(autouse=True)
def _create_test_database():
    """No-op override: unit tests do not need a live database."""
    yield


@pytest.fixture(scope="session", autouse=True)
def _pg_host():
    """No-op override: unit tests do not need a live database."""
    return "unit-no-db"
