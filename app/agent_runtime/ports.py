"""Ports used by the Native Agent runtime core."""

from __future__ import annotations

from typing import Any, Protocol


class SceneStore(Protocol):
    """Read scene configuration for a run."""

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        """Return a scene by id."""


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
    ) -> None:
        """Update run lifecycle state."""

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


class ToolPolicyStore(Protocol):
    """Read tool governance policy."""

    def get_policy(self, tool_name: str) -> dict[str, Any] | None:
        """Return a persisted policy or None when no override exists."""
