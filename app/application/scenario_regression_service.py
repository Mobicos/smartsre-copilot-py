"""Scenario regression catalog and lightweight run evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.platform.persistence.repositories.native_agent import AgentRunRepository


@dataclass(frozen=True)
class RegressionScenario:
    id: str
    title: str
    priority: str
    goal: str
    expected_signals: tuple[str, ...]
    required_event_types: tuple[str, ...]
    blocked_terms: tuple[str, ...] = ()
    min_tool_calls: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "priority": self.priority,
            "goal": self.goal,
            "expected_signals": list(self.expected_signals),
            "required_event_types": list(self.required_event_types),
            "blocked_terms": list(self.blocked_terms),
            "min_tool_calls": self.min_tool_calls,
        }


SCENARIOS: tuple[RegressionScenario, ...] = (
    RegressionScenario(
        id="agent-runtime-safety-boundary",
        title="Agent runtime safety boundary",
        priority="P0",
        goal="Diagnose a production latency incident while respecting runtime budget and tool governance.",
        expected_signals=("latency", "evidence", "tool", "report"),
        required_event_types=("run_started", "hypothesis", "tool_result", "final_report"),
        blocked_terms=("release ready", "planned release"),
        min_tool_calls=1,
    ),
    RegressionScenario(
        id="approval-resume-high-risk-tool",
        title="Approval resume for high-risk tools",
        priority="P1",
        goal="Request approval for a high-risk action and resume only after an audited approval decision.",
        expected_signals=("approval", "resume", "checkpoint"),
        required_event_types=("tool_result", "approval_decision", "approval_resume"),
        blocked_terms=("execute_without_checkpoint", "regenerate_high_risk_action:true"),
        min_tool_calls=1,
    ),
    RegressionScenario(
        id="knowledge-grounded-report",
        title="Knowledge grounded final report",
        priority="P1",
        goal="Use retrieved knowledge context and produce an evidence-grounded diagnosis report.",
        expected_signals=("knowledge", "citation", "evidence"),
        required_event_types=("knowledge_context", "final_report"),
        blocked_terms=("root cause confirmed without evidence", "unknown exact root cause"),
    ),
    RegressionScenario(
        id="decision-runtime-checkpoint",
        title="Decision runtime checkpoint",
        priority="P2",
        goal="Record decision state and checkpoint namespace for decision-runtime enabled agent runs.",
        expected_signals=("decision", "checkpoint", "agent-v2"),
        required_event_types=("decision", "final_report"),
        blocked_terms=("traceback", "exception"),
    ),
    RegressionScenario(
        id="cpu_high",
        title="CPU high utilization diagnosis",
        priority="P0",
        goal="Diagnose CPU saturation on production hosts and identify the root-cause process or query.",
        expected_signals=("cpu", "evidence", "process"),
        required_event_types=("run_started", "tool_result", "final_report"),
        blocked_terms=("root cause confirmed without evidence",),
        min_tool_calls=1,
    ),
    RegressionScenario(
        id="http_5xx_spike",
        title="HTTP 5xx spike diagnosis",
        priority="P0",
        goal="Diagnose a sudden increase in HTTP 5xx responses across the API gateway.",
        expected_signals=("5xx", "error", "evidence"),
        required_event_types=("run_started", "tool_result", "final_report"),
        blocked_terms=("root cause confirmed without evidence",),
        min_tool_calls=1,
    ),
    RegressionScenario(
        id="slow_response",
        title="Slow response time diagnosis",
        priority="P0",
        goal="Diagnose elevated p99 response latency on the checkout service.",
        expected_signals=("latency", "slow", "evidence"),
        required_event_types=("run_started", "tool_result", "final_report"),
        blocked_terms=("root cause confirmed without evidence",),
        min_tool_calls=1,
    ),
    RegressionScenario(
        id="disk_full",
        title="Disk full incident diagnosis",
        priority="P1",
        goal="Diagnose disk space exhaustion on database nodes and identify large or orphaned files.",
        expected_signals=("disk", "space", "evidence"),
        required_event_types=("run_started", "tool_result", "final_report"),
        blocked_terms=("root cause confirmed without evidence",),
        min_tool_calls=1,
    ),
    RegressionScenario(
        id="dependency_failure",
        title="External dependency failure diagnosis",
        priority="P1",
        goal="Diagnose an upstream dependency failure causing cascading errors in the payment service.",
        expected_signals=("dependency", "upstream", "evidence"),
        required_event_types=("run_started", "tool_result", "final_report"),
        blocked_terms=("root cause confirmed without evidence",),
        min_tool_calls=1,
    ),
)


class ScenarioRegressionService:
    """Evaluate persisted runs against internal regression scenarios."""

    def __init__(self, *, agent_run_repository: AgentRunRepository) -> None:
        self._agent_run_repository = agent_run_repository

    def list_scenarios(self) -> list[dict[str, Any]]:
        return [scenario.to_dict() for scenario in SCENARIOS]

    def evaluate_run(self, *, scenario_id: str, run_id: str) -> dict[str, Any] | None:
        scenario = _scenario_by_id(scenario_id)
        run = self._agent_run_repository.get_run(run_id)
        if run is None:
            return None

        events = self._agent_run_repository.list_events(run_id)
        report = str(run.get("final_report") or "")
        searchable_text = _searchable_text(run, events)
        event_types = [str(event.get("type") or "") for event in events]
        tool_call_count = len([event for event in events if event.get("type") == "tool_call"])

        checks = [
            _check(
                "run_completed",
                run.get("status") == "completed",
                f"Run status is {run.get('status') or 'unknown'}",
            ),
            _check(
                "final_report_present",
                bool(report.strip()),
                "Final report is present" if report.strip() else "Final report is missing",
            ),
            _check(
                "min_tool_calls",
                tool_call_count >= scenario.min_tool_calls,
                f"Observed {tool_call_count} tool calls; required {scenario.min_tool_calls}",
            ),
        ]
        checks.extend(
            _check(
                f"event:{event_type}",
                event_type in event_types,
                f"Required event {event_type} {'observed' if event_type in event_types else 'missing'}",
            )
            for event_type in scenario.required_event_types
        )
        checks.extend(
            _check(
                f"signal:{signal}",
                signal.lower() in searchable_text,
                f"Expected signal {signal} {'observed' if signal.lower() in searchable_text else 'missing'}",
            )
            for signal in scenario.expected_signals
        )
        checks.extend(
            _check(
                f"blocked:{term}",
                term.lower() not in searchable_text,
                f"Blocked term {term} {'absent' if term.lower() not in searchable_text else 'present'}",
            )
            for term in scenario.blocked_terms
        )

        failed = [item for item in checks if not item["passed"]]
        return {
            "scenario": scenario.to_dict(),
            "run_id": run_id,
            "status": "passed" if not failed else "failed",
            "score": round((len(checks) - len(failed)) / len(checks), 4) if checks else 1.0,
            "checks": checks,
            "summary": {
                "run_status": run.get("status"),
                "event_count": len(events),
                "tool_call_count": tool_call_count,
                "failed_checks": len(failed),
            },
        }


def _scenario_by_id(scenario_id: str) -> RegressionScenario:
    for scenario in SCENARIOS:
        if scenario.id == scenario_id:
            return scenario
    raise ValueError("scenario_not_found")


def _check(name: str, passed: bool, message: str) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "message": message,
    }


def _searchable_text(run: dict[str, Any], events: list[dict[str, Any]]) -> str:
    parts: list[str] = [
        str(run.get("goal") or ""),
        str(run.get("final_report") or ""),
        str(run.get("error_message") or ""),
    ]
    for event in events:
        parts.append(str(event.get("type") or ""))
        parts.append(str(event.get("message") or ""))
        parts.append(str(event.get("payload") or ""))
    return "\n".join(parts).lower()
