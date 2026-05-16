from __future__ import annotations

from typing import Any

from app.agent_runtime.decision import AgentDecision
from app.agent_runtime.loop import LoopStep
from app.agent_runtime.runtime import EventRecorder


class _RunStore:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def append_event(self, run_id: str, *, event_type: str, stage: str, message: str, payload):
        self.events.append(
            {
                "run_id": run_id,
                "type": event_type,
                "stage": stage,
                "message": message,
                "payload": payload,
            }
        )


def test_event_recorder_persists_loop_step_metrics_as_decision_event():
    run_store = _RunStore()
    recorder = EventRecorder(run_store)  # type: ignore[arg-type]
    step = LoopStep(
        step_index=2,
        decision=AgentDecision(
            action_type="call_tool",
            selected_tool="SearchLog",
            reasoning_summary="Check logs for errors.",
        ),
        token_usage=20,
        token_usage_detail={"total": 20, "source": "provider_usage"},
        cost_estimate={"total_cost": 0.001, "source": "provider_usage"},
    )

    event = recorder.record_loop_step("run-1", step)

    assert event.type == "decision"
    assert event.stage == "decision"
    assert event.message == "Check logs for errors."
    assert event.payload["step_index"] == 2
    assert event.payload["decision"]["selected_tool"] == "SearchLog"
    assert event.payload["token_usage"] == {"total": 20, "source": "provider_usage"}
    assert event.payload["cost_estimate"] == {"total_cost": 0.001, "source": "provider_usage"}
    assert run_store.events[0]["payload"] == event.payload
