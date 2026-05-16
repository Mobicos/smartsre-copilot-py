from __future__ import annotations

from app.agent_runtime.decision import (
    DecisionProviderFactory,
    DeterministicDecisionProvider,
    LangChainQwenDecisionInvoker,
    QwenDecisionProvider,
    build_initial_decision_state,
)
from app.agent_runtime.ports import DecisionProvider
from app.core.config import AppSettings


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


class _UsageAwareQwenInvoker:
    def __call__(self, _state):
        return (
            '{"action_type":"final_report","reasoning_summary":"enough evidence","confidence":0.9}'
        )

    def get_token_usage(self):
        return {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total": 20,
            "source": "provider_usage",
        }

    def get_cost_estimate(self):
        return {
            "currency": "USD",
            "total_cost": 0.0012,
            "source": "provider_usage",
        }


def test_qwen_provider_implements_decision_provider_port():
    provider = QwenDecisionProvider(_UsageAwareQwenInvoker())
    state = build_initial_decision_state(
        run_id="run-1",
        goal="Diagnose latency",
        workspace_id="workspace-1",
        scene_id="scene-1",
        available_tools=["SearchLog"],
    )

    decision = provider.decide(state)

    assert isinstance(provider, DecisionProvider)
    assert decision.action_type == "final_report"
    assert provider.get_token_usage()["total"] == 20
    assert provider.get_token_usage()["source"] == "provider_usage"
    assert provider.get_cost_estimate()["total_cost"] == 0.0012


class _FakeQwenResponse:
    content = (
        '{"action_type":"final_report","reasoning_summary":"enough evidence","confidence":0.9}'
    )
    usage_metadata = {
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
    }


class _FakeQwenChatModel:
    def invoke(self, _messages):
        return _FakeQwenResponse()


def test_langchain_qwen_invoker_exposes_provider_token_usage():
    invoker = LangChainQwenDecisionInvoker(_FakeQwenChatModel())
    provider = QwenDecisionProvider(invoker)
    state = build_initial_decision_state(
        run_id="run-1",
        goal="Diagnose latency",
        workspace_id="workspace-1",
        scene_id="scene-1",
        available_tools=["SearchLog"],
    )

    provider.decide(state)

    assert provider.get_token_usage() == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total": 20,
        "source": "provider_usage",
    }
    assert provider.get_cost_estimate()["total_cost"] > 0
    assert provider.get_cost_estimate()["source"] == "heuristic_from_provider_tokens"


def test_provider_factory_creates_deterministic_provider_from_settings():
    factory = DecisionProviderFactory(AppSettings(agent_decision_provider="deterministic"))

    provider = factory.create_provider()
    runtime = factory.create_runtime()

    assert isinstance(provider, DeterministicDecisionProvider)
    assert runtime.consume_provider_fallback_events() == []


def test_provider_factory_creates_qwen_provider_with_fallback():
    created_models: list[str] = []

    def chat_model_factory(model_name: str):
        created_models.append(model_name)
        return _FakeQwenChatModel()

    factory = DecisionProviderFactory(
        AppSettings(agent_decision_provider="qwen", dashscope_model="qwen-max"),
        chat_model_factory=chat_model_factory,
    )

    provider = factory.create_provider()
    runtime = factory.create_runtime()

    assert isinstance(provider, QwenDecisionProvider)
    assert created_models == ["qwen-max", "qwen-max"]
    assert isinstance(runtime._fallback_provider, DeterministicDecisionProvider)
