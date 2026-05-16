"""Ports used by the Native Agent runtime core."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.agent_runtime.decision import AgentDecision, AgentDecisionState


@runtime_checkable
class SceneStore(Protocol):
    """Read scene configuration for a run."""

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        """Return a scene by id."""


@runtime_checkable
class AgentRunStore(Protocol):
    """Persist run lifecycle and trajectory events."""

    def create_run(
        self,
        *,
        workspace_id: str,
        scene_id: str,
        session_id: str,
        goal: str,
    ) -> str:
        """Create an agent run and return its id."""

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        final_report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update run lifecycle state."""

    def update_run_metrics(self, run_id: str, **metrics: Any) -> None:
        """Persist run-level observability metrics."""

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Return a persisted run snapshot."""

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        """Return persisted trajectory events for a run."""

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        """Append a trajectory event."""


@runtime_checkable
class ToolPolicyStore(Protocol):
    """Read tool governance policy."""

    def get_policy(self, tool_name: str) -> dict[str, Any] | None:
        """Return a persisted policy or None when no override exists."""


@runtime_checkable
class AgentMemoryStore(Protocol):
    """Persist and retrieve cross-session Agent memories."""

    def search_memory(
        self,
        *,
        workspace_id: str,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Return relevant memories for a new run."""

    def create_memory(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        conclusion_text: str,
        conclusion_type: str = "final_report",
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist one memory item and return its id."""


@runtime_checkable
class DecisionProvider(Protocol):
    """Provider interface for deterministic or model-backed decisions."""

    def decide(self, state: AgentDecisionState) -> AgentDecision:
        """Return the next structured decision."""

    def get_token_usage(self) -> dict[str, Any]:
        """Return provider token usage for the latest or deterministic decision."""

    def get_cost_estimate(self) -> dict[str, Any]:
        """Return provider cost estimate for the latest or deterministic decision."""
