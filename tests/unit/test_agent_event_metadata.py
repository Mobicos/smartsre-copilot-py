from __future__ import annotations

from app.platform.persistence.repositories.native_agent import _event_metadata_columns
from app.platform.persistence.schema import AgentEvent


def test_agent_event_schema_has_runtime_metric_columns():
    assert "step_index" in AgentEvent.model_fields
    assert "evidence_quality" in AgentEvent.model_fields
    assert "recovery_action" in AgentEvent.model_fields
    assert "token_usage" in AgentEvent.model_fields
    assert "cost_estimate" in AgentEvent.model_fields


def test_event_metadata_columns_are_derived_from_payload():
    payload = {
        "step_index": 2,
        "quality": "weak",
        "recovery_action": "try_alternative",
        "token_usage": {"total": 20, "source": "provider_usage"},
        "cost_estimate": {"total_cost": 0.001, "source": "provider_usage"},
    }

    assert _event_metadata_columns(payload) == {
        "step_index": 2,
        "evidence_quality": "weak",
        "recovery_action": "try_alternative",
        "token_usage": {"total": 20, "source": "provider_usage"},
        "cost_estimate": {"total_cost": 0.001, "source": "provider_usage"},
    }
