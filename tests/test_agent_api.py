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
