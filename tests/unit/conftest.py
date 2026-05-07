"""Unit test conftest — overrides the autouse DB fixture from tests/conftest.py."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_postgres_database():
    """No-op override: unit tests do not need a live database."""
    yield
