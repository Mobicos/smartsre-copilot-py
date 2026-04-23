from __future__ import annotations

from app.services.aiops_service import AIOpsService


def test_aiops_planner_event_reports_plan_size():
    service = AIOpsService()

    event = service._format_planner_event({"plan": ["check alerts", "inspect logs"]})

    assert event["type"] == "plan"
    assert event["stage"] == "plan_created"
    assert event["plan"] == ["check alerts", "inspect logs"]


def test_aiops_executor_event_reports_last_completed_step():
    service = AIOpsService()

    event = service._format_executor_event(
        {
            "plan": ["inspect traces"],
            "past_steps": [("check alerts", "alert summary")],
        }
    )

    assert event["type"] == "step_complete"
    assert event["stage"] == "step_executed"
    assert event["current_step"] == "check alerts"
    assert event["remaining_steps"] == 1


def test_aiops_replanner_event_returns_report_when_response_exists():
    service = AIOpsService()

    event = service._format_replanner_event({"response": "final report", "plan": []})

    assert event == {
        "type": "report",
        "stage": "final_report",
        "message": "最终报告已生成",
        "report": "final report",
    }
