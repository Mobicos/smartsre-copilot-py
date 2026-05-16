"""Unit tests for collaborative intervention subsystem (Phase 10 / T054-T060)."""

from __future__ import annotations

from app.agent_runtime.decision import (
    AgentDecision,
    AgentDecisionState,
    AgentGoalContract,
    EvidenceAssessment,
)
from app.agent_runtime.intervention import (
    Intervention,
    InterventionBridge,
    InterventionType,
)
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_state(
    goal: str = "diagnose OOM",
    run_id: str = "run-int-1",
    workspace_id: str = "ws-1",
) -> AgentDecisionState:
    return AgentDecisionState(
        run_id=run_id,
        goal=AgentGoalContract(goal=goal, workspace_id=workspace_id),
    )


def _make_intervention(
    *,
    run_id: str = "run-int-1",
    intervention_type: InterventionType = InterventionType.INJECT_EVIDENCE,
    payload: dict | None = None,
) -> Intervention:
    return Intervention(
        intervention_id="iv-test-001",
        run_id=run_id,
        intervention_type=intervention_type,
        payload=payload or {"content": "test evidence", "source": "human"},
    )


class _DeterministicProvider:
    """Provider that always returns call_tool with low confidence."""

    provider_name = "test"

    def __init__(self, confidence: float = 0.1):
        self._confidence = confidence
        self.seen_states: list[AgentDecisionState] = []

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        self.seen_states.append(state)
        return AgentDecision(
            action_type="call_tool",
            selected_tool="check_memory",
            reasoning_summary="checking memory",
            evidence=EvidenceAssessment(quality="weak"),
            confidence=self._confidence,
        )


class _TerminalProvider:
    """Provider that immediately returns final_report."""

    provider_name = "test"

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        return AgentDecision(
            action_type="final_report",
            selected_tool=None,
            reasoning_summary="done",
            evidence=EvidenceAssessment(quality="strong", summary="complete"),
            confidence=0.9,
        )


# ---------------------------------------------------------------------------
# InterventionBridge unit tests (T059)
# ---------------------------------------------------------------------------


class TestInterventionBridge:
    def test_add_and_pending(self):
        bridge = InterventionBridge()
        iv = _make_intervention()
        bridge.add(iv)
        assert len(bridge.pending("run-int-1")) == 1
        assert bridge.pending("run-int-1")[0].intervention_id == "iv-test-001"

    def test_pending_empty_for_unknown_run(self):
        bridge = InterventionBridge()
        assert bridge.pending("nonexistent") == []

    def test_mark_applied_removes_from_pending(self):
        bridge = InterventionBridge()
        iv = _make_intervention()
        bridge.add(iv)
        assert len(bridge.pending("run-int-1")) == 1
        bridge.mark_applied(iv)
        assert bridge.pending("run-int-1") == []

    def test_clear_removes_all_for_run(self):
        bridge = InterventionBridge()
        bridge.add(_make_intervention(payload={"content": "a"}))
        bridge.add(_make_intervention(payload={"content": "b"}))
        assert len(bridge.pending("run-int-1")) == 2
        bridge.clear("run-int-1")
        assert bridge.pending("run-int-1") == []

    def test_isolation_between_runs(self):
        bridge = InterventionBridge()
        bridge.add(_make_intervention(run_id="run-1"))
        bridge.add(_make_intervention(run_id="run-2"))
        assert len(bridge.pending("run-1")) == 1
        assert len(bridge.pending("run-2")) == 1
        bridge.clear("run-1")
        assert bridge.pending("run-1") == []
        assert len(bridge.pending("run-2")) == 1


# ---------------------------------------------------------------------------
# Apply helpers tests
# ---------------------------------------------------------------------------


class TestApplyInjectedEvidence:
    def test_inject_adds_observation(self):
        state = _make_state()
        iv = _make_intervention(
            payload={"content": "检查数据库连接池", "source": "human", "confidence": 0.95}
        )
        new_state = InterventionBridge.apply_injected_evidence(iv, state)
        assert len(new_state.observations) == 1
        obs = new_state.observations[0]
        assert obs.summary == "检查数据库连接池"
        assert obs.source == "human"
        assert obs.confidence == 0.95

    def test_inject_preserves_existing_observations(self):
        state = _make_state()
        from app.agent_runtime.decision import AgentObservation

        state = state.model_copy(
            update={
                "observations": [
                    AgentObservation(source="tool", summary="existing", confidence=0.8)
                ]
            }
        )
        iv = _make_intervention()
        new_state = InterventionBridge.apply_injected_evidence(iv, state)
        assert len(new_state.observations) == 2
        assert new_state.observations[0].summary == "existing"
        assert new_state.observations[1].summary == "test evidence"


class TestApplyReplaceDecision:
    def test_replace_tool(self):
        original = AgentDecision(
            action_type="call_tool",
            selected_tool="old_tool",
            reasoning_summary="old reasoning",
            evidence=EvidenceAssessment(quality="weak"),
            confidence=0.1,
        )
        iv = _make_intervention(
            intervention_type=InterventionType.REPLACE_TOOL_CALL,
            payload={"selected_tool": "new_tool", "reasoning_summary": "new reasoning"},
        )
        replaced = InterventionBridge.apply_replace_decision(iv, original)
        assert replaced.selected_tool == "new_tool"
        assert replaced.reasoning_summary == "new reasoning"

    def test_replace_no_payload_returns_original(self):
        original = AgentDecision(
            action_type="call_tool",
            selected_tool="tool_a",
            reasoning_summary="original",
            evidence=EvidenceAssessment(quality="weak"),
            confidence=0.5,
        )
        iv = _make_intervention(
            intervention_type=InterventionType.REPLACE_TOOL_CALL,
            payload={},
        )
        result = InterventionBridge.apply_replace_decision(iv, original)
        assert result is original


class TestApplyModifyGoal:
    def test_modify_goal(self):
        state = _make_state(goal="original goal")
        iv = _make_intervention(
            intervention_type=InterventionType.MODIFY_GOAL,
            payload={"goal": "updated goal"},
        )
        new_state = InterventionBridge.apply_modify_goal(iv, state)
        assert new_state.goal.goal == "updated goal"

    def test_modify_goal_preserves_workspace(self):
        state = _make_state(goal="original", workspace_id="ws-1")
        iv = _make_intervention(
            intervention_type=InterventionType.MODIFY_GOAL,
            payload={"goal": "updated"},
        )
        new_state = InterventionBridge.apply_modify_goal(iv, state)
        assert new_state.goal.workspace_id == "ws-1"

    def test_modify_goal_no_payload_returns_unchanged(self):
        state = _make_state(goal="keep this")
        iv = _make_intervention(
            intervention_type=InterventionType.MODIFY_GOAL,
            payload={},
        )
        new_state = InterventionBridge.apply_modify_goal(iv, state)
        assert new_state.goal.goal == "keep this"


# ---------------------------------------------------------------------------
# Loop integration: inject_evidence
# ---------------------------------------------------------------------------


class TestLoopInjectEvidence:
    def test_injected_evidence_appears_in_provider_state(self):
        bridge = InterventionBridge()
        bridge.add(
            _make_intervention(
                payload={"content": "数据库连接池耗尽", "source": "human"},
            )
        )
        provider = _DeterministicProvider()
        loop = BoundedReActLoop(
            provider=provider,
            intervention_bridge=bridge,
        )
        state = _make_state()
        result = loop.run(state, LoopBudget(max_steps=1, max_time_seconds=10))
        assert result.termination_reason == "max_steps_reached"
        # The provider should have seen the injected observation
        assert len(provider.seen_states) == 1
        observations = provider.seen_states[0].observations
        assert any("数据库连接池耗尽" in obs.summary for obs in observations)

    def test_intervention_marked_applied_after_use(self):
        bridge = InterventionBridge()
        iv = _make_intervention()
        bridge.add(iv)
        loop = BoundedReActLoop(
            provider=_DeterministicProvider(),
            intervention_bridge=bridge,
        )
        loop.run(_make_state(), LoopBudget(max_steps=1, max_time_seconds=10))
        assert bridge.pending("run-int-1") == []


# ---------------------------------------------------------------------------
# Loop integration: replace_tool_call
# ---------------------------------------------------------------------------


class TestLoopReplaceToolCall:
    def test_replace_tool_call_overrides_decision(self):
        bridge = InterventionBridge()
        bridge.add(
            _make_intervention(
                intervention_type=InterventionType.REPLACE_TOOL_CALL,
                payload={"selected_tool": "query_database", "reasoning_summary": "human override"},
            )
        )

        class _ToolCaptor:
            """Provider whose decision gets replaced, then immediately terminal."""

            provider_name = "test"

            def __init__(self):
                self.decisions: list[AgentDecision] = []

            def decide(self, state: AgentDecisionState) -> AgentDecision:
                d = AgentDecision(
                    action_type="call_tool",
                    selected_tool="wrong_tool",
                    reasoning_summary="wrong",
                    evidence=EvidenceAssessment(quality="weak"),
                    confidence=0.1,
                )
                self.decisions.append(d)
                # After first step, return terminal
                return d

        # Need a tool_executor for call_tool to actually execute
        def _noop_executor(decision: AgentDecision):
            return {"status": "ok", "data": "tool result"}

        captor = _ToolCaptor()
        loop = BoundedReActLoop(
            provider=captor,
            intervention_bridge=bridge,
            tool_executor=_noop_executor,
        )
        result = loop.run(_make_state(), LoopBudget(max_steps=2, max_time_seconds=10))
        # First step: the decision should be replaced before act phase
        first_step = result.steps[0]
        # The tool_executor was called, and the step's decision had the replaced tool
        assert first_step.decision.selected_tool == "query_database"
        assert first_step.decision.reasoning_summary == "human override"


# ---------------------------------------------------------------------------
# Loop integration: low-confidence auto-handoff (T057)
# ---------------------------------------------------------------------------


class TestLowConfidenceHandoff:
    def test_consecutive_low_confidence_triggers_handoff(self):
        loop = BoundedReActLoop(
            provider=_DeterministicProvider(confidence=0.1),
            max_low_confidence_steps=3,
            low_confidence_threshold=0.3,
        )
        state = _make_state()
        result = loop.run(state, LoopBudget(max_steps=5, max_time_seconds=60))
        assert result.termination_reason == "low_confidence_handoff"
        # Should have run 3 steps before handoff
        assert len(result.steps) == 3

    def test_confidence_reset_on_high_confidence_step(self):
        class _MixedProvider:
            provider_name = "test"

            def __init__(self):
                self._call_count = 0

            def decide(self, state: AgentDecisionState) -> AgentDecision:
                self._call_count += 1
                # Steps 1-2: low confidence, step 3: high confidence, step 4-6: low again
                if self._call_count == 3:
                    conf = 0.8
                else:
                    conf = 0.1
                return AgentDecision(
                    action_type="call_tool",
                    selected_tool="check",
                    reasoning_summary="checking",
                    evidence=EvidenceAssessment(quality="weak"),
                    confidence=conf,
                )

        loop = BoundedReActLoop(
            provider=_MixedProvider(),
            max_low_confidence_steps=3,
            low_confidence_threshold=0.3,
        )
        result = loop.run(_make_state(), LoopBudget(max_steps=6, max_time_seconds=60))
        # Step 3 resets counter, so steps 4-6 hit 3 consecutive low again
        assert result.termination_reason == "low_confidence_handoff"
        assert len(result.steps) == 6

    def test_no_handoff_when_confidence_above_threshold(self):
        loop = BoundedReActLoop(
            provider=_DeterministicProvider(confidence=0.5),
            max_low_confidence_steps=3,
            low_confidence_threshold=0.3,
        )
        result = loop.run(_make_state(), LoopBudget(max_steps=5, max_time_seconds=60))
        # All steps above threshold — runs to max_steps
        assert result.termination_reason == "max_steps_reached"

    def test_handoff_disabled_when_max_none(self):
        loop = BoundedReActLoop(
            provider=_DeterministicProvider(confidence=0.1),
            max_low_confidence_steps=None,
        )
        result = loop.run(_make_state(), LoopBudget(max_steps=5, max_time_seconds=60))
        assert result.termination_reason == "max_steps_reached"


# ---------------------------------------------------------------------------
# Loop integration: modify_goal
# ---------------------------------------------------------------------------


class TestLoopModifyGoal:
    def test_modify_goal_appears_in_provider_state(self):
        bridge = InterventionBridge()
        bridge.add(
            _make_intervention(
                intervention_type=InterventionType.MODIFY_GOAL,
                payload={"goal": "investigate memory leak"},
            )
        )
        provider = _DeterministicProvider()
        loop = BoundedReActLoop(
            provider=provider,
            intervention_bridge=bridge,
        )
        state = _make_state(goal="original goal")
        loop.run(state, LoopBudget(max_steps=1, max_time_seconds=10))
        assert provider.seen_states[0].goal.goal == "investigate memory leak"
