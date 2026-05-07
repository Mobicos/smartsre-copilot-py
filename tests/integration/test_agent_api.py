from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import native_agent


def test_native_agent_api_creates_scene_and_runs_agent(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    workspace_response = client.post(
        "/api/workspaces",
        json={"name": "SRE", "description": "on-call"},
    )
    workspace_id = workspace_response.json()["data"]["id"]

    scene_response = client.post(
        "/api/scenes",
        json={
            "workspace_id": workspace_id,
            "name": "Default Diagnosis",
            "description": "demo scene",
            "tool_names": [],
        },
    )
    scene_id = scene_response.json()["data"]["id"]

    run_response = client.post(
        "/api/agent/runs",
        json={
            "scene_id": scene_id,
            "session_id": "session-1",
            "goal": "diagnose alerts",
        },
    )
    run_data = run_response.json()["data"]
    events_response = client.get(f"/api/agent/runs/{run_data['run_id']}/events")

    assert workspace_response.status_code == 200
    assert scene_response.status_code == 200
    assert run_response.status_code == 200
    assert run_data["status"] == "completed"
    assert events_response.json()["data"][0]["type"] == "run_started"


def test_native_agent_api_lists_runs_after_agent_execution(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    workspace_id = client.post("/api/workspaces", json={"name": "SRE"}).json()["data"]["id"]
    scene_id = client.post(
        "/api/scenes",
        json={"workspace_id": workspace_id, "name": "Default Diagnosis"},
    ).json()["data"]["id"]

    run = client.post(
        "/api/agent/runs",
        json={"scene_id": scene_id, "session_id": "session-1", "goal": "diagnose alerts"},
    ).json()["data"]
    runs_response = client.get("/api/agent/runs")

    assert runs_response.status_code == 200
    assert runs_response.json()["data"][0]["run_id"] == run["run_id"]


def test_native_agent_api_merges_partial_tool_policy_updates(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    first_response = client.patch(
        "/api/tools/SearchLog/policy",
        json={"risk_level": "high", "approval_required": True},
    )
    second_response = client.patch(
        "/api/tools/SearchLog/policy",
        json={"enabled": False},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["data"] == {
        "tool_name": "SearchLog",
        "scope": "diagnosis",
        "risk_level": "high",
        "capability": None,
        "enabled": False,
        "approval_required": True,
        "created_at": second_response.json()["data"]["created_at"],
        "updated_at": second_response.json()["data"]["updated_at"],
    }


def test_native_agent_api_accepts_product_feedback_ratings(monkeypatch):
    app = FastAPI()
    app.include_router(native_agent.router, prefix="/api")
    client = TestClient(app)

    workspace_id = client.post("/api/workspaces", json={"name": "SRE"}).json()["data"]["id"]
    scene_id = client.post(
        "/api/scenes",
        json={"workspace_id": workspace_id, "name": "Default Diagnosis"},
    ).json()["data"]["id"]
    run_id = client.post(
        "/api/agent/runs",
        json={"scene_id": scene_id, "session_id": "session-1", "goal": "diagnose alerts"},
    ).json()["data"]["run_id"]

    response = client.post(
        f"/api/agent/runs/{run_id}/feedback",
        json={"rating": "helpful", "comment": "Good evidence trail"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["feedback_id"]
