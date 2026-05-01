"""Native Agent platform repositories."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import (
    AgentEvent,
    AgentFeedback,
    AgentRun,
    KnowledgeBase,
    Scene,
    SceneKnowledgeBase,
    SceneTool,
    ToolPolicy,
    Workspace,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _json_dumps(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}


class WorkspaceRepository:
    """Cloud Mate style workspace repository."""

    def create_workspace(self, *, name: str, description: str | None = None) -> str:
        workspace_id = str(uuid.uuid4())
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            session.add(
                Workspace(
                    workspace_id=workspace_id,
                    name=name,
                    description=description,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        return workspace_id

    def list_workspaces(self) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            rows = session.exec(select(Workspace).order_by(col(Workspace.created_at).asc())).all()
        return [
            {
                "id": row.workspace_id,
                "name": row.name,
                "description": row.description,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
            for row in rows
        ]

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            row = session.get(Workspace, workspace_id)
        if row is None:
            return None
        return {
            "id": row.workspace_id,
            "name": row.name,
            "description": row.description,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
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
        knowledge_base_id = str(uuid.uuid4())
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            session.add(
                KnowledgeBase(
                    knowledge_base_id=knowledge_base_id,
                    workspace_id=workspace_id,
                    name=name,
                    description=description,
                    version=version,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        return knowledge_base_id

    def list_by_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            rows = session.exec(
                select(KnowledgeBase)
                .where(KnowledgeBase.workspace_id == workspace_id)
                .order_by(col(KnowledgeBase.created_at).asc())
            ).all()
        return [self._row_to_dict(row) for row in rows]

    def get_many(self, knowledge_base_ids: list[str]) -> list[dict[str, Any]]:
        if not knowledge_base_ids:
            return []
        with Session(bind=get_engine()) as session:
            rows = session.exec(
                select(KnowledgeBase).where(
                    col(KnowledgeBase.knowledge_base_id).in_(knowledge_base_ids)
                )
            ).all()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "id": row.knowledge_base_id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "description": row.description,
            "version": row.version,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
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
        scene_id = str(uuid.uuid4())
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            session.add(
                Scene(
                    scene_id=scene_id,
                    workspace_id=workspace_id,
                    name=name,
                    description=description,
                    agent_config=_json_dumps(agent_config),
                    created_at=now,
                    updated_at=now,
                )
            )
            for kb_id in knowledge_base_ids or []:
                session.add(SceneKnowledgeBase(scene_id=scene_id, knowledge_base_id=kb_id))
            for tool_name in tool_names or []:
                session.add(SceneTool(scene_id=scene_id, tool_name=tool_name))
            session.commit()
        return scene_id

    def list_scenes(self, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            statement = select(Scene).order_by(col(Scene.created_at).asc())
            if workspace_id:
                statement = statement.where(Scene.workspace_id == workspace_id)
            rows = session.exec(statement).all()
        return [self._row_to_dict(row, include_links=False) for row in rows]

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            scene = session.get(Scene, scene_id)
            if scene is None:
                return None

            kb_statement = (
                select(KnowledgeBase)
                .join(SceneKnowledgeBase)
                .where(SceneKnowledgeBase.scene_id == scene_id)
                .order_by(col(KnowledgeBase.created_at).asc())
            )
            knowledge_rows = session.exec(kb_statement).all()

            tool_statement = (
                select(SceneTool)
                .where(SceneTool.scene_id == scene_id)
                .order_by(col(SceneTool.tool_name).asc())
            )
            tool_rows = session.exec(tool_statement).all()

        result = self._row_to_dict(scene, include_links=True)
        result["knowledge_bases"] = [
            KnowledgeBaseRepository._row_to_dict(kb) for kb in knowledge_rows
        ]
        result["tools"] = [t.tool_name for t in tool_rows]
        return result

    @staticmethod
    def _row_to_dict(row: Any, *, include_links: bool) -> dict[str, Any]:
        scene = {
            "id": row.scene_id,
            "workspace_id": row.workspace_id,
            "name": row.name,
            "description": row.description,
            "agent_config": _json_loads(row.agent_config),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
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
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            existing = session.get(ToolPolicy, tool_name)
            if existing is not None:
                existing.scope = scope
                existing.risk_level = risk_level
                existing.capability = capability
                existing.enabled = enabled
                existing.approval_required = approval_required
                existing.updated_at = now
            else:
                existing = ToolPolicy(
                    tool_name=tool_name,
                    scope=scope,
                    risk_level=risk_level,
                    capability=capability,
                    enabled=enabled,
                    approval_required=approval_required,
                    created_at=now,
                    updated_at=now,
                )
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return self._row_to_dict(existing)

    def get_policy(self, tool_name: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            row = session.get(ToolPolicy, tool_name)
        return self._row_to_dict(row) if row is not None else None

    def list_policies(self) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            rows = session.exec(select(ToolPolicy).order_by(col(ToolPolicy.tool_name).asc())).all()
        return [self._row_to_dict(row) for row in rows]

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "tool_name": row.tool_name,
            "scope": row.scope,
            "risk_level": row.risk_level,
            "capability": row.capability,
            "enabled": bool(row.enabled),
            "approval_required": bool(row.approval_required),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
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
        run_id = str(uuid.uuid4())
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            session.add(
                AgentRun(
                    run_id=run_id,
                    workspace_id=workspace_id,
                    scene_id=scene_id,
                    session_id=session_id,
                    status="running",
                    goal=goal,
                    created_at=now,
                    updated_at=now,
                )
            )
            session.commit()
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        final_report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with Session(bind=get_engine()) as session:
            run = session.get(AgentRun, run_id)
            if run is None:
                return
            run.status = status
            if final_report is not None:
                run.final_report = final_report
            if error_message is not None:
                run.error_message = error_message
            run.updated_at = _utc_now()
            session.add(run)
            session.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            row = session.get(AgentRun, run_id)
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
        with Session(bind=get_engine()) as session:
            session.add(
                AgentEvent(
                    run_id=run_id,
                    event_type=event_type,
                    stage=stage,
                    message=message,
                    payload=_json_dumps(payload),
                    created_at=_utc_now(),
                )
            )
            session.commit()

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            rows = session.exec(
                select(AgentEvent)
                .where(AgentEvent.run_id == run_id)
                .order_by(col(AgentEvent.created_at).asc(), col(AgentEvent.id).asc())
            ).all()
        return [
            {
                "id": row.id,
                "run_id": row.run_id,
                "type": row.event_type,
                "stage": row.stage,
                "message": row.message,
                "payload": json.loads(row.payload) if row.payload else None,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        return {
            "run_id": row.run_id,
            "workspace_id": row.workspace_id,
            "scene_id": row.scene_id,
            "session_id": row.session_id,
            "status": row.status,
            "goal": row.goal,
            "final_report": row.final_report,
            "error_message": row.error_message,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
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
        feedback_id = str(uuid.uuid4())
        with Session(bind=get_engine()) as session:
            session.add(
                AgentFeedback(
                    feedback_id=feedback_id,
                    run_id=run_id,
                    rating=rating,
                    comment=comment,
                    created_at=_utc_now(),
                )
            )
            session.commit()
        return feedback_id

    def list_feedback(self, run_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            rows = session.exec(
                select(AgentFeedback)
                .where(AgentFeedback.run_id == run_id)
                .order_by(col(AgentFeedback.created_at).asc())
            ).all()
        return [
            {
                "feedback_id": row.feedback_id,
                "run_id": row.run_id,
                "rating": row.rating,
                "comment": row.comment,
                "created_at": row.created_at,
            }
            for row in rows
        ]


workspace_repository = WorkspaceRepository()
knowledge_base_repository = KnowledgeBaseRepository()
scene_repository = SceneRepository()
tool_policy_repository = ToolPolicyRepository()
agent_run_repository = AgentRunRepository()
agent_feedback_repository = AgentFeedbackRepository()
