"""Native Agent platform repositories."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.platform.persistence.database import database_manager


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def _json_dumps(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


class WorkspaceRepository:
    """Cloud Mate style workspace repository."""

    def create_workspace(self, *, name: str, description: str | None = None) -> str:
        database_manager.initialize()
        workspace_id = str(uuid.uuid4())
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO workspaces (workspace_id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, name, description, now, now),
            )
        return workspace_id

    def list_workspaces(self) -> list[dict[str, Any]]:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.fetchall(
                """
                SELECT workspace_id, name, description, created_at, updated_at
                FROM workspaces
                ORDER BY created_at ASC
                """
            )
        return [
            {
                "id": row["workspace_id"],
                "name": row["name"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.fetchone(
                """
                SELECT workspace_id, name, description, created_at, updated_at
                FROM workspaces
                WHERE workspace_id = ?
                """,
                (workspace_id,),
            )
        if row is None:
            return None
        return {
            "id": row["workspace_id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class KnowledgeBaseRepository:
    """Knowledge base metadata repository."""

    def create_knowledge_base(
        self,
        workspace_id: str,
        *,
        name: str,
        description: str | None = None,
        version: str = "0.0.1",
    ) -> str:
        database_manager.initialize()
        knowledge_base_id = str(uuid.uuid4())
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO knowledge_bases (
                    knowledge_base_id, workspace_id, name, description, version,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (knowledge_base_id, workspace_id, name, description, version, now, now),
            )
        return knowledge_base_id

    def list_by_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.fetchall(
                """
                SELECT knowledge_base_id, workspace_id, name, description, version,
                       created_at, updated_at
                FROM knowledge_bases
                WHERE workspace_id = ?
                ORDER BY created_at ASC
                """,
                (workspace_id,),
            )
        return [self._row_to_dict(row) for row in rows]

    def get_many(self, knowledge_base_ids: list[str]) -> list[dict[str, Any]]:
        if not knowledge_base_ids:
            return []
        database_manager.initialize()
        rows: list[Any] = []
        with database_manager.get_connection() as connection:
            for knowledge_base_id in knowledge_base_ids:
                row = connection.fetchone(
                    """
                    SELECT knowledge_base_id, workspace_id, name, description, version,
                           created_at, updated_at
                    FROM knowledge_bases
                    WHERE knowledge_base_id = ?
                    """,
                    (knowledge_base_id,),
                )
                if row is not None:
                    rows.append(row)
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "id": row["knowledge_base_id"],
            "workspace_id": row["workspace_id"],
            "name": row["name"],
            "description": row["description"],
            "version": row["version"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class SceneRepository:
    """Operational scene repository."""

    def create_scene(
        self,
        workspace_id: str,
        *,
        name: str,
        description: str | None = None,
        knowledge_base_ids: list[str] | None = None,
        tool_names: list[str] | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> str:
        database_manager.initialize()
        scene_id = str(uuid.uuid4())
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO scenes (
                    scene_id, workspace_id, name, description, agent_config,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene_id,
                    workspace_id,
                    name,
                    description,
                    _json_dumps(agent_config),
                    now,
                    now,
                ),
            )
            for knowledge_base_id in knowledge_base_ids or []:
                connection.execute(
                    """
                    INSERT INTO scene_knowledge_bases (scene_id, knowledge_base_id)
                    VALUES (?, ?)
                    """,
                    (scene_id, knowledge_base_id),
                )
            for tool_name in tool_names or []:
                connection.execute(
                    "INSERT INTO scene_tools (scene_id, tool_name) VALUES (?, ?)",
                    (scene_id, tool_name),
                )
        return scene_id

    def list_scenes(self, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        database_manager.initialize()
        query = """
            SELECT scene_id, workspace_id, name, description, agent_config,
                   created_at, updated_at
            FROM scenes
        """
        params: list[Any] = []
        if workspace_id:
            query += " WHERE workspace_id = ?"
            params.append(workspace_id)
        query += " ORDER BY created_at ASC"
        with database_manager.get_connection() as connection:
            rows = connection.fetchall(query, params)
        return [self._row_to_dict(row, include_links=False) for row in rows]

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.fetchone(
                """
                SELECT scene_id, workspace_id, name, description, agent_config,
                       created_at, updated_at
                FROM scenes
                WHERE scene_id = ?
                """,
                (scene_id,),
            )
            if row is None:
                return None
            knowledge_rows = connection.fetchall(
                """
                SELECT kb.knowledge_base_id, kb.workspace_id, kb.name, kb.description,
                       kb.version, kb.created_at, kb.updated_at
                FROM knowledge_bases kb
                JOIN scene_knowledge_bases skb
                  ON skb.knowledge_base_id = kb.knowledge_base_id
                WHERE skb.scene_id = ?
                ORDER BY kb.created_at ASC
                """,
                (scene_id,),
            )
            tool_rows = connection.fetchall(
                """
                SELECT tool_name
                FROM scene_tools
                WHERE scene_id = ?
                ORDER BY tool_name ASC
                """,
                (scene_id,),
            )

        scene = self._row_to_dict(row, include_links=True)
        scene["knowledge_bases"] = [
            KnowledgeBaseRepository._row_to_dict(knowledge_row) for knowledge_row in knowledge_rows
        ]
        scene["tools"] = [tool_row["tool_name"] for tool_row in tool_rows]
        return scene

    @staticmethod
    def _row_to_dict(row: Any, *, include_links: bool) -> dict[str, Any]:
        scene = {
            "id": row["scene_id"],
            "workspace_id": row["workspace_id"],
            "name": row["name"],
            "description": row["description"],
            "agent_config": _json_loads(row["agent_config"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if include_links:
            scene["knowledge_bases"] = []
            scene["tools"] = []
        return scene


class ToolPolicyRepository:
    """Tool execution policy repository."""

    def upsert_policy(
        self,
        tool_name: str,
        *,
        scope: str = "diagnosis",
        risk_level: str = "low",
        capability: str | None = None,
        enabled: bool = True,
        approval_required: bool = False,
    ) -> dict[str, Any]:
        database_manager.initialize()
        now = utc_now()
        existing = self.get_policy(tool_name)
        created_at = existing["created_at"] if existing else now
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO tool_policies (
                    tool_name, scope, risk_level, capability, enabled,
                    approval_required, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_name)
                DO UPDATE SET
                    scope = excluded.scope,
                    risk_level = excluded.risk_level,
                    capability = excluded.capability,
                    enabled = excluded.enabled,
                    approval_required = excluded.approval_required,
                    updated_at = excluded.updated_at
                """,
                (
                    tool_name,
                    scope,
                    risk_level,
                    capability,
                    int(enabled),
                    int(approval_required),
                    created_at,
                    now,
                ),
            )
        policy = self.get_policy(tool_name)
        if policy is None:
            raise RuntimeError(f"failed to persist tool policy: {tool_name}")
        return policy

    def get_policy(self, tool_name: str) -> dict[str, Any] | None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.fetchone(
                """
                SELECT tool_name, scope, risk_level, capability, enabled,
                       approval_required, created_at, updated_at
                FROM tool_policies
                WHERE tool_name = ?
                """,
                (tool_name,),
            )
        return self._row_to_dict(row) if row is not None else None

    def list_policies(self) -> list[dict[str, Any]]:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.fetchall(
                """
                SELECT tool_name, scope, risk_level, capability, enabled,
                       approval_required, created_at, updated_at
                FROM tool_policies
                ORDER BY tool_name ASC
                """
            )
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "tool_name": row["tool_name"],
            "scope": row["scope"],
            "risk_level": row["risk_level"],
            "capability": row["capability"],
            "enabled": bool(row["enabled"]),
            "approval_required": bool(row["approval_required"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class AgentRunRepository:
    """Native agent run and trajectory repository."""

    def create_run(
        self,
        *,
        workspace_id: str,
        scene_id: str | None,
        session_id: str,
        goal: str,
    ) -> str:
        database_manager.initialize()
        run_id = str(uuid.uuid4())
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, workspace_id, scene_id, session_id, status, goal,
                    final_report, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, workspace_id, scene_id, session_id, "running", goal, None, None, now, now),
            )
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        final_report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                UPDATE agent_runs
                SET status = ?, final_report = COALESCE(?, final_report),
                    error_message = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (status, final_report, error_message, utc_now(), run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.fetchone(
                """
                SELECT run_id, workspace_id, scene_id, session_id, status, goal,
                       final_report, error_message, created_at, updated_at
                FROM agent_runs
                WHERE run_id = ?
                """,
                (run_id,),
            )
        return self._row_to_dict(row) if row is not None else None

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_events (
                    run_id, event_type, stage, message, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, event_type, stage, message, _json_dumps(payload), utc_now()),
            )

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.fetchall(
                """
                SELECT id, run_id, event_type, stage, message, payload, created_at
                FROM agent_events
                WHERE run_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (run_id,),
            )
        return [
            {
                "id": row["id"],
                "run_id": row["run_id"],
                "type": row["event_type"],
                "stage": row["stage"],
                "message": row["message"],
                "payload": json.loads(row["payload"]) if row["payload"] else None,
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "run_id": row["run_id"],
            "workspace_id": row["workspace_id"],
            "scene_id": row["scene_id"],
            "session_id": row["session_id"],
            "status": row["status"],
            "goal": row["goal"],
            "final_report": row["final_report"],
            "error_message": row["error_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


class AgentFeedbackRepository:
    """Agent run feedback repository."""

    def create_feedback(
        self,
        run_id: str,
        *,
        rating: str,
        comment: str | None = None,
    ) -> str:
        database_manager.initialize()
        feedback_id = str(uuid.uuid4())
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_feedback (feedback_id, run_id, rating, comment, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (feedback_id, run_id, rating, comment, utc_now()),
            )
        return feedback_id

    def list_feedback(self, run_id: str) -> list[dict[str, Any]]:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.fetchall(
                """
                SELECT feedback_id, run_id, rating, comment, created_at
                FROM agent_feedback
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (run_id,),
            )
        return [
            {
                "feedback_id": row["feedback_id"],
                "run_id": row["run_id"],
                "rating": row["rating"],
                "comment": row["comment"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]


workspace_repository = WorkspaceRepository()
knowledge_base_repository = KnowledgeBaseRepository()
scene_repository = SceneRepository()
tool_policy_repository = ToolPolicyRepository()
agent_run_repository = AgentRunRepository()
agent_feedback_repository = AgentFeedbackRepository()
