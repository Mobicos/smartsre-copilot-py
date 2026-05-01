from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import pytest

from app.application.aiops_application_service import AIOpsApplicationService
from app.platform.persistence import (
    aiops_run_repository,
    conversation_repository,
    scene_repository,
    workspace_repository,
)
from app.security.auth import Principal


class StaticRuntime:
    def __init__(self) -> None:
        self.goals: list[str] = []

    async def run(
        self,
        *,
        scene_id: str,
        session_id: str,
        goal: str,
        principal: Principal,
    ) -> AsyncGenerator[dict, None]:
        self.goals.append(goal)
        yield {
            "type": "run_started",
            "stage": "start",
            "run_id": "native-run",
            "message": "started",
        }
        yield {
            "type": "complete",
            "stage": "complete",
            "run_id": "native-run",
            "status": "completed",
            "final_report": "# report",
        }


@pytest.mark.asyncio
async def test_aiops_stream_uses_native_runtime_and_preserves_complete_event():
    runtime = StaticRuntime()
    service = AIOpsApplicationService(
        agent_runtime=runtime,
        aiops_run_repository=aiops_run_repository,
        conversation_repository=conversation_repository,
        workspace_repository=workspace_repository,
        scene_repository=scene_repository,
    )

    events = [
        json.loads(chunk["data"])
        async for chunk in service.stream_diagnosis(
            "session-1",
            task_input="Investigate checkout latency",
            principal=Principal(role="admin", subject="pytest"),
        )
    ]

    assert runtime.goals == ["Investigate checkout latency"]
    assert events[-1]["type"] == "complete"
    assert events[-1]["stage"] == "diagnosis_complete"
    assert events[-1]["diagnosis"]["report"] == "# report"
    assert events[-1]["native_run_id"] == "native-run"
