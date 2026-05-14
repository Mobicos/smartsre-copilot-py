from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent_runtime import (
    AgentDecision,
    AgentDecisionRuntime,
    AgentGoalContract,
    AgentHypothesis,
    AgentObservation,
    EvidenceAssessment,
    FinalReportContract,
    QwenDecisionProvider,
    RecoveryDecision,
    RuntimeBudget,
    StopCondition,
    SuccessCriteria,
    build_initial_decision_state,
)
from app.domains.native_agent.schemas import AgentRunCreateRequest


def test_goal_contract_requires_explicit_decision_fields():
    contract = AgentGoalContract(
        goal="Diagnose checkout 5xx spike",
        success_criteria=[
            SuccessCriteria(description="Identify the most likely failing dependency")
        ],
        stop_condition=StopCondition(max_steps=3, max_minutes=2, confidence_threshold=0.75),
        priority="P0",
        workspace_id="workspace-1",
        scene_id="scene-1",
        allowed_tools=["SearchLog"],
        trace_id="trace-1",
    )

    assert contract.goal == "Diagnose checkout 5xx spike"
    assert contract.priority == "P0"
    assert contract.stop_condition.max_steps == 3
    assert contract.success_criteria[0].description == (
        "Identify the most likely failing dependency"
    )
    assert contract.trace_id == "trace-1"


def test_goal_contract_rejects_private_reasoning_outputs():
    with pytest.raises(ValidationError):
        AgentGoalContract(
            goal="Diagnose latency",
            prohibited_outputs=["private_chain_of_thought"],
            reasoning_policy="persist private chain-of-thought",
        )


def test_build_initial_state_includes_observation_and_hypothesis_queue():
    state = build_initial_decision_state(
        run_id="run-1",
        goal="Diagnose latency",
        workspace_id="workspace-1",
        scene_id="scene-1",
        available_tools=["SearchLog"],
        budget=RuntimeBudget(max_steps=2, remaining_steps=2),
    )

    assert state.goal.trace_id == "run-1"
    assert state.observations == [
        AgentObservation(source="user_goal", summary="Diagnose latency", confidence=1.0)
    ]
    assert state.hypothesis_queue == [
        AgentHypothesis(
            hypothesis_id="hypothesis-1",
            summary="验证目标相关的日志、指标、告警和近期变更。",
            priority=1,
            confidence=0.5,
        )
    ]


def test_qwen_provider_recovers_on_unknown_tool_and_low_confidence():
    unknown_tool_provider = QwenDecisionProvider(
        lambda _state: (
            '{"action_type":"call_tool","reasoning_summary":"Call unsupported tool",'
            '"selected_tool":"RestartService","confidence":0.9}'
        )
    )
    low_confidence_provider = QwenDecisionProvider(
        lambda _state: (
            '{"action_type":"final_report","reasoning_summary":"Evidence is weak","confidence":0.1}'
        )
    )
    state = build_initial_decision_state(
        run_id="run-1",
        goal="Diagnose latency",
        workspace_id="workspace-1",
        scene_id="scene-1",
        available_tools=["SearchLog"],
    )

    unknown_tool_decision = unknown_tool_provider.decide(state)
    low_confidence_decision = low_confidence_provider.decide(state)

    assert unknown_tool_decision.action_type == "recover"
    assert unknown_tool_decision.recovery.reason == "unknown_tool"
    assert low_confidence_decision.action_type == "recover"
    assert low_confidence_decision.recovery.reason == "low_confidence"


def test_qwen_provider_recovers_on_invalid_json_and_empty_response():
    invalid_json_provider = QwenDecisionProvider(lambda _state: "not json")
    empty_response_provider = QwenDecisionProvider(lambda _state: "")
    state = build_initial_decision_state(
        run_id="run-1",
        goal="Diagnose latency",
        workspace_id="workspace-1",
        scene_id="scene-1",
        available_tools=["SearchLog"],
    )

    invalid_json_decision = invalid_json_provider.decide(state)
    empty_response_decision = empty_response_provider.decide(state)

    assert invalid_json_decision.action_type == "recover"
    assert invalid_json_decision.recovery.reason == "invalid_model_output"
    assert empty_response_decision.action_type == "recover"
    assert empty_response_decision.recovery.reason == "invalid_model_output"


def test_decision_runtime_graph_nodes_update_state_and_cache_compiled_graph():
    runtime = AgentDecisionRuntime()
    state = build_initial_decision_state(
        run_id="run-1",
        goal="Diagnose latency",
        workspace_id="workspace-1",
        scene_id="scene-1",
        available_tools=["SearchLog"],
        budget=RuntimeBudget(max_steps=2, remaining_steps=2, remaining_tool_calls=1),
    )

    result = runtime.run_graph_once(state)

    assert runtime.build_graph() is runtime.build_graph()
    assert result.decisions[-1].action_type == "call_tool"
    assert result.executed_tools == ["SearchLog"]
    assert result.budget.remaining_steps == 1
    assert result.budget.remaining_tool_calls == 0
    assert result.evidence[-1].quality == "weak"


def test_final_report_contract_separates_facts_inferences_and_handoff():
    report = FinalReportContract(
        summary="Evidence is insufficient for a confirmed root cause.",
        verified_facts=["SearchLog returned no matching errors"],
        inferences=["The issue may be outside the configured log scope"],
        recommendations=["Escalate to the service owner with the captured evidence"],
        citations=[{"source": "SearchLog", "event_id": "event-1"}],
        confidence=0.4,
        handoff_required=True,
        handoff_reason="insufficient_evidence",
    )

    payload = report.to_event_payload()

    assert payload["handoff_required"] is True
    assert payload["handoff_reason"] == "insufficient_evidence"
    assert payload["verified_facts"] == ["SearchLog returned no matching errors"]
    assert payload["inferences"] == ["The issue may be outside the configured log scope"]


def test_decision_payload_exposes_selected_action_and_actual_evidence():
    decision = AgentDecision(
        action_type="recover",
        reasoning_summary="Tool evidence was empty, so recovery is required.",
        selected_tool="SearchLog",
        selected_action="call_tool",
        tool_arguments={"query": "latency"},
        expected_evidence=["Log errors around the incident window"],
        actual_evidence=EvidenceAssessment(
            quality="empty",
            summary="No matching log entries were returned.",
            confidence=0.0,
        ),
        recovery=RecoveryDecision(
            required=True,
            reason="empty_evidence",
            next_action="handoff",
        ),
        confidence=0.2,
    )

    payload = decision.to_event_payload()

    assert payload["selected_action"] == "call_tool"
    assert payload["decision_status"] == "recover"
    assert payload["actual_evidence"]["quality"] == "empty"
    assert payload["handoff_reason"] == "empty_evidence"


def test_agent_run_request_accepts_goal_governance_fields():
    request = AgentRunCreateRequest(
        scene_id="scene-1",
        session_id="session-1",
        goal="Diagnose checkout 5xx",
        success_criteria=["Identify the most likely failing dependency"],
        stop_condition={"max_steps": 3, "max_minutes": 2, "confidence_threshold": 0.75},
        priority="P0",
    )

    assert request.success_criteria == ["Identify the most likely failing dependency"]
    assert request.stop_condition == {
        "max_steps": 3,
        "max_minutes": 2,
        "confidence_threshold": 0.75,
    }
    assert request.priority == "P0"


def test_agent_run_request_rejects_invalid_priority():
    with pytest.raises(ValidationError):
        AgentRunCreateRequest(
            scene_id="scene-1",
            goal="Diagnose checkout 5xx",
            priority="SEV0",
        )
