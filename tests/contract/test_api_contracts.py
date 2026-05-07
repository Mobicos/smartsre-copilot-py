"""API contract tests.

Validates that API route handlers return responses conforming to
expected schemas. These tests use FastAPI's TestClient and do not
require a running server.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert isinstance(data["status"], str)


# ---------------------------------------------------------------------------
# Agent workspace endpoints
# ---------------------------------------------------------------------------


def test_list_workspaces_returns_array(client):
    response = client.get("/api/workspaces")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_create_workspace_requires_name(client):
    response = client.post("/api/workspaces", json={})
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Agent scene endpoints
# ---------------------------------------------------------------------------


def test_list_scenes_returns_array(client):
    response = client.get("/api/scenes")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


# ---------------------------------------------------------------------------
# Agent tools endpoints
# ---------------------------------------------------------------------------


def test_list_tools_returns_array(client):
    response = client.get("/api/tools")
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    if data:
        tool = data[0]
        assert "name" in tool
        assert "description" in tool


# ---------------------------------------------------------------------------
# Agent runs endpoints
# ---------------------------------------------------------------------------


def test_list_runs_returns_array(client):
    response = client.get("/api/agent/runs")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


# ---------------------------------------------------------------------------
# Agent approvals endpoints
# ---------------------------------------------------------------------------


def test_list_approvals_returns_array(client):
    response = client.get("/api/agent/approvals")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


# ---------------------------------------------------------------------------
# Scenario regression endpoints
# ---------------------------------------------------------------------------


def test_list_scenarios_returns_array(client):
    response = client.get("/api/scenario-regression/scenarios")
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------


def test_upload_requires_file(client):
    response = client.post("/api/upload")
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# OpenAPI spec
# ---------------------------------------------------------------------------


def test_openapi_spec_available(client):
    response = client.get("/api/contracts/openapi")
    assert response.status_code == 200
    body = response.json()
    data = body.get("data", body)
    assert "current" in data
