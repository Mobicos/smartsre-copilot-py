from __future__ import annotations

from app.agent_runtime.decision import DeterministicDecisionProvider
from app.agent_runtime.ports import DecisionProvider


def test_deterministic_provider_implements_decision_provider_port():
    provider = DeterministicDecisionProvider()

    assert isinstance(provider, DecisionProvider)
    assert provider.get_token_usage() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total": 0,
        "source": "deterministic_zero",
    }
    assert provider.get_cost_estimate() == {
        "currency": "USD",
        "total_cost": 0.0,
        "source": "deterministic_zero",
    }
