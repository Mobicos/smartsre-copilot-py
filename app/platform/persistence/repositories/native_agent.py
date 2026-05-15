"""Native Agent platform repositories."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, update
from sqlmodel import Session, col, select

from app.agent_runtime.ports import AgentRunStore, SceneStore, ToolPolicyStore
from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import (
    AgentEvent,
    AgentFeedback,
    AgentMemory,
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

    def create_workspace_with_session(
        self,
        db: Session,
        *,
        name: str,
        description: str | None = None,
    ) -> str:
        workspace_id = str(uuid.uuid4())
        now = _utc_now()
        db.add(
            Workspace(
                workspace_id=workspace_id,
                name=name,
                description=description,
                created_at=now,
                updated_at=now,
            )
        )
        return workspace_id

    def create_workspace(self, *, name: str, description: str | None = None) -> str:
        with Session(bind=get_engine()) as db:
            workspace_id = self.create_workspace_with_session(
                db, name=name, description=description
            )
            db.commit()
        return workspace_id

    def list_workspaces_with_session(self, db: Session) -> list[dict[str, Any]]:
        rows = db.exec(select(Workspace).order_by(col(Workspace.created_at).asc())).all()
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

    def list_workspaces(self) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_workspaces_with_session(db)

    def get_workspace_with_session(self, db: Session, workspace_id: str) -> dict[str, Any] | None:
        row = db.get(Workspace, workspace_id)
        if row is None:
            return None
        return {
            "id": row.workspace_id,
            "name": row.name,
            "description": row.description,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def get_workspace(self, workspace_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.get_workspace_with_session(db, workspace_id)


class KnowledgeBaseRepository:
    """Knowledge base metadata repository."""

    def create_knowledge_base_with_session(
        self,
        db: Session,
        workspace_id: str,
        *,
        name: str,
        description: str | None = None,
        version: str = "0.0.1",
    ) -> str:
        knowledge_base_id = str(uuid.uuid4())
        now = _utc_now()
        db.add(
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
        return knowledge_base_id

    def create_knowledge_base(
        self,
        workspace_id: str,
        *,
        name: str,
        description: str | None = None,
        version: str = "0.0.1",
    ) -> str:
        with Session(bind=get_engine()) as db:
            knowledge_base_id = self.create_knowledge_base_with_session(
                db, workspace_id, name=name, description=description, version=version
            )
            db.commit()
        return knowledge_base_id

    def list_by_workspace_with_session(
        self, db: Session, workspace_id: str
    ) -> list[dict[str, Any]]:
        rows = db.exec(
            select(KnowledgeBase)
            .where(KnowledgeBase.workspace_id == workspace_id)
            .order_by(col(KnowledgeBase.created_at).asc())
        ).all()
        return [self._row_to_dict(row) for row in rows]

    def list_by_workspace(self, workspace_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_by_workspace_with_session(db, workspace_id)

    def get_many_with_session(
        self, db: Session, knowledge_base_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not knowledge_base_ids:
            return []
        rows = db.exec(
            select(KnowledgeBase).where(
                col(KnowledgeBase.knowledge_base_id).in_(knowledge_base_ids)
            )
        ).all()
        return [self._row_to_dict(row) for row in rows]

    def get_many(self, knowledge_base_ids: list[str]) -> list[dict[str, Any]]:
        if not knowledge_base_ids:
            return []
        with Session(bind=get_engine()) as db:
            return self.get_many_with_session(db, knowledge_base_ids)

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


class SceneRepository(SceneStore):
    """Operational scene repository."""

    def create_scene_with_session(
        self,
        db: Session,
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
        db.add(
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
            db.add(SceneKnowledgeBase(scene_id=scene_id, knowledge_base_id=kb_id))
        for tool_name in tool_names or []:
            db.add(SceneTool(scene_id=scene_id, tool_name=tool_name))
        return scene_id

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
        with Session(bind=get_engine()) as db:
            scene_id = self.create_scene_with_session(
                db,
                workspace_id,
                name=name,
                description=description,
                knowledge_base_ids=knowledge_base_ids,
                tool_names=tool_names,
                agent_config=agent_config,
            )
            db.commit()
        return scene_id

    def list_scenes_with_session(
        self, db: Session, *, workspace_id: str | None = None
    ) -> list[dict[str, Any]]:
        statement = select(Scene).order_by(col(Scene.created_at).asc())
        if workspace_id:
            statement = statement.where(Scene.workspace_id == workspace_id)
        rows = db.exec(statement).all()
        return [self._row_to_dict(row, include_links=False) for row in rows]

    def list_scenes(self, *, workspace_id: str | None = None) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_scenes_with_session(db, workspace_id=workspace_id)

    def get_scene_with_session(self, db: Session, scene_id: str) -> dict[str, Any] | None:
        scene = db.get(Scene, scene_id)
        if scene is None:
            return None

        kb_statement = (
            select(KnowledgeBase)
            .join(SceneKnowledgeBase)
            .where(SceneKnowledgeBase.scene_id == scene_id)
            .order_by(col(KnowledgeBase.created_at).asc())
        )
        knowledge_rows = db.exec(kb_statement).all()

        tool_statement = (
            select(SceneTool)
            .where(SceneTool.scene_id == scene_id)
            .order_by(col(SceneTool.tool_name).asc())
        )
        tool_rows = db.exec(tool_statement).all()

        result = self._row_to_dict(scene, include_links=True)
        result["knowledge_bases"] = [
            KnowledgeBaseRepository._row_to_dict(kb) for kb in knowledge_rows
        ]
        result["tools"] = [t.tool_name for t in tool_rows]
        return result

    def get_scene(self, scene_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.get_scene_with_session(db, scene_id)

    def delete_scene_with_session(self, db: Session, scene_id: str) -> bool:
        scene = db.get(Scene, scene_id)
        if scene is None:
            return False
        db.exec(
            update(AgentRun)
            .where(col(AgentRun.scene_id) == scene_id)
            .values(scene_id=None, updated_at=_utc_now())
        )
        db.exec(delete(SceneKnowledgeBase).where(col(SceneKnowledgeBase.scene_id) == scene_id))
        db.exec(delete(SceneTool).where(col(SceneTool.scene_id) == scene_id))
        db.delete(scene)
        return True

    def delete_scene(self, scene_id: str) -> bool:
        with Session(bind=get_engine()) as db:
            deleted = self.delete_scene_with_session(db, scene_id)
            db.commit()
            return deleted

    def delete_scenes_by_name_prefix(self, name_prefix: str) -> int:
        with Session(bind=get_engine()) as db:
            rows = db.exec(select(Scene).where(Scene.name.startswith(name_prefix))).all()
            deleted_count = 0
            for scene in rows:
                if self.delete_scene_with_session(db, scene.scene_id):
                    deleted_count += 1
            db.commit()
            return deleted_count

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


class ToolPolicyRepository(ToolPolicyStore):
    """Tool execution policy repository."""

    def upsert_policy_with_session(
        self,
        db: Session,
        tool_name: str,
        *,
        scope: str = "diagnosis",
        risk_level: str = "low",
        capability: str | None = None,
        enabled: bool = True,
        approval_required: bool = False,
    ) -> dict[str, Any]:
        now = _utc_now()
        existing = db.get(ToolPolicy, tool_name)
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
        db.add(existing)
        db.flush()
        db.refresh(existing)
        return self._row_to_dict(existing)

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
        with Session(bind=get_engine()) as db:
            result = self.upsert_policy_with_session(
                db,
                tool_name,
                scope=scope,
                risk_level=risk_level,
                capability=capability,
                enabled=enabled,
                approval_required=approval_required,
            )
            db.commit()
        return result

    def get_policy_with_session(self, db: Session, tool_name: str) -> dict[str, Any] | None:
        row = db.get(ToolPolicy, tool_name)
        return self._row_to_dict(row) if row is not None else None

    def get_policy(self, tool_name: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.get_policy_with_session(db, tool_name)

    def list_policies_with_session(self, db: Session) -> list[dict[str, Any]]:
        rows = db.exec(select(ToolPolicy).order_by(col(ToolPolicy.tool_name).asc())).all()
        return [self._row_to_dict(row) for row in rows]

    def list_policies(self) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_policies_with_session(db)

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


class AgentRunRepository(AgentRunStore):
    """Native agent run and trajectory repository."""

    def create_run_with_session(
        self,
        db: Session,
        *,
        workspace_id: str,
        scene_id: str | None,
        session_id: str,
        goal: str,
    ) -> str:
        run_id = str(uuid.uuid4())
        now = _utc_now()
        db.add(
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
        return run_id

    def create_run(
        self,
        *,
        workspace_id: str,
        scene_id: str | None,
        session_id: str,
        goal: str,
    ) -> str:
        with Session(bind=get_engine()) as db:
            run_id = self.create_run_with_session(
                db,
                workspace_id=workspace_id,
                scene_id=scene_id,
                session_id=session_id,
                goal=goal,
            )
            db.commit()
        return run_id

    def update_run_with_session(
        self,
        db: Session,
        run_id: str,
        *,
        status: str,
        final_report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run = db.get(AgentRun, run_id)
        if run is None:
            return
        run.status = status
        if final_report is not None:
            run.final_report = final_report
        if error_message is not None:
            run.error_message = error_message
        run.updated_at = _utc_now()
        db.add(run)

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        final_report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with Session(bind=get_engine()) as db:
            self.update_run_with_session(
                db,
                run_id,
                status=status,
                final_report=final_report,
                error_message=error_message,
            )
            db.commit()

    def update_run_metrics_with_session(
        self,
        db: Session,
        run_id: str,
        *,
        runtime_version: str | None = None,
        trace_id: str | None = None,
        model_name: str | None = None,
        decision_provider: str | None = None,
        step_count: int | None = None,
        tool_call_count: int | None = None,
        latency_ms: int | None = None,
        error_type: str | None = None,
        approval_state: str | None = None,
        retrieval_count: int | None = None,
        token_usage: dict[str, Any] | None = None,
        cost_estimate: dict[str, Any] | None = None,
        handoff_reason: str | None = None,
    ) -> None:
        run = db.get(AgentRun, run_id)
        if run is None:
            return
        run.runtime_version = runtime_version
        run.trace_id = trace_id
        run.model_name = model_name
        run.decision_provider = decision_provider
        run.step_count = step_count
        run.tool_call_count = tool_call_count
        run.latency_ms = latency_ms
        run.error_type = error_type
        run.approval_state = approval_state
        run.retrieval_count = retrieval_count
        run.token_usage = token_usage
        run.cost_estimate = cost_estimate
        run.handoff_reason = handoff_reason
        db.add(run)

    def update_run_metrics(self, run_id: str, **metrics: Any) -> None:
        with Session(bind=get_engine()) as db:
            self.update_run_metrics_with_session(db, run_id, **metrics)
            db.commit()

    def get_run_with_session(self, db: Session, run_id: str) -> dict[str, Any] | None:
        row = db.get(AgentRun, run_id)
        return self._row_to_dict(row) if row is not None else None

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            return self.get_run_with_session(db, run_id)

    def list_runs_with_session(self, db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = db.exec(
            select(AgentRun).order_by(col(AgentRun.created_at).desc()).limit(limit)
        ).all()
        return [self._row_to_dict(row) for row in rows]

    def list_runs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_runs_with_session(db, limit=limit)

    def append_event_with_session(
        self,
        db: Session,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        db.add(
            AgentEvent(
                run_id=run_id,
                event_type=event_type,
                stage=stage,
                message=message,
                payload=_json_dumps(payload),
                created_at=_utc_now(),
            )
        )

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with Session(bind=get_engine()) as db:
            self.append_event_with_session(
                db,
                run_id,
                event_type=event_type,
                stage=stage,
                message=message,
                payload=payload,
            )
            db.commit()

    def list_events_with_session(self, db: Session, run_id: str) -> list[dict[str, Any]]:
        rows = db.exec(
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

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_events_with_session(db, run_id)

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
            "runtime_version": row.runtime_version,
            "trace_id": row.trace_id,
            "model_name": row.model_name,
            "decision_provider": row.decision_provider,
            "step_count": row.step_count,
            "tool_call_count": row.tool_call_count,
            "latency_ms": row.latency_ms,
            "error_type": row.error_type,
            "approval_state": row.approval_state,
            "retrieval_count": row.retrieval_count,
            "cost_estimate": row.cost_estimate,
            "handoff_reason": row.handoff_reason,
            "token_usage": row.token_usage,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }


class AgentFeedbackRepository:
    """Agent run feedback repository."""

    def create_feedback_with_session(
        self,
        db: Session,
        run_id: str,
        *,
        rating: str,
        comment: str | None = None,
        correction: str | None = None,
        badcase_flag: bool = False,
        original_report: str | None = None,
        review_status: str = "pending",
    ) -> str:
        feedback_id = str(uuid.uuid4())
        db.add(
            AgentFeedback(
                feedback_id=feedback_id,
                run_id=run_id,
                rating=rating,
                comment=comment,
                correction=correction,
                badcase_flag=badcase_flag,
                original_report=original_report,
                review_status=review_status,
                created_at=_utc_now(),
            )
        )
        return feedback_id

    def create_feedback(
        self,
        run_id: str,
        *,
        rating: str,
        comment: str | None = None,
        correction: str | None = None,
        badcase_flag: bool = False,
        original_report: str | None = None,
        review_status: str = "pending",
    ) -> str:
        with Session(bind=get_engine()) as db:
            feedback_id = self.create_feedback_with_session(
                db,
                run_id,
                rating=rating,
                comment=comment,
                correction=correction,
                badcase_flag=badcase_flag,
                original_report=original_report,
                review_status=review_status,
            )
            db.commit()
        return feedback_id

    def list_feedback_with_session(self, db: Session, run_id: str) -> list[dict[str, Any]]:
        rows = db.exec(
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
                "correction": row.correction,
                "badcase_flag": row.badcase_flag,
                "original_report": row.original_report,
                "review_status": row.review_status,
                "review_note": row.review_note,
                "reviewed_by": row.reviewed_by,
                "reviewed_at": row.reviewed_at,
                "knowledge_status": row.knowledge_status,
                "knowledge_task_id": row.knowledge_task_id,
                "knowledge_filename": row.knowledge_filename,
                "promoted_at": row.promoted_at,
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def list_feedback(self, run_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            return self.list_feedback_with_session(db, run_id)

    def list_badcases(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            rows = db.exec(
                select(AgentFeedback, AgentRun)
                .join(AgentRun, col(AgentFeedback.run_id) == col(AgentRun.run_id))
                .where(col(AgentFeedback.badcase_flag).is_(True))
                .order_by(col(AgentFeedback.created_at).desc())
                .limit(limit)
            ).all()
        return [
            {
                **self._feedback_row_to_dict(feedback),
                "run": AgentRunRepository._row_to_dict(run),
            }
            for feedback, run in rows
        ]

    def get_badcase(self, feedback_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as db:
            row = db.exec(
                select(AgentFeedback, AgentRun)
                .join(AgentRun, col(AgentFeedback.run_id) == col(AgentRun.run_id))
                .where(col(AgentFeedback.feedback_id) == feedback_id)
                .where(col(AgentFeedback.badcase_flag).is_(True))
            ).first()
        if row is None:
            return None
        feedback, run = row
        return {
            **self._feedback_row_to_dict(feedback),
            "run": AgentRunRepository._row_to_dict(run),
        }

    def review_badcase(
        self,
        feedback_id: str,
        *,
        review_status: str,
        review_note: str | None,
        reviewed_by: str | None,
    ) -> dict[str, Any] | None:
        reviewed_at = _utc_now()
        with Session(bind=get_engine()) as db:
            db.exec(
                update(AgentFeedback)
                .where(col(AgentFeedback.feedback_id) == feedback_id)
                .where(col(AgentFeedback.badcase_flag).is_(True))
                .values(
                    review_status=review_status,
                    review_note=review_note,
                    reviewed_by=reviewed_by,
                    reviewed_at=reviewed_at,
                )
            )
            db.commit()
            row = db.exec(
                select(AgentFeedback).where(AgentFeedback.feedback_id == feedback_id)
            ).first()
            if row is None or not row.badcase_flag:
                return None
            return self._feedback_row_to_dict(row)

    def mark_badcase_knowledge_promotion(
        self,
        feedback_id: str,
        *,
        knowledge_status: str,
        knowledge_task_id: str,
        knowledge_filename: str,
    ) -> dict[str, Any] | None:
        promoted_at = _utc_now()
        with Session(bind=get_engine()) as db:
            db.exec(
                update(AgentFeedback)
                .where(col(AgentFeedback.feedback_id) == feedback_id)
                .where(col(AgentFeedback.badcase_flag).is_(True))
                .values(
                    knowledge_status=knowledge_status,
                    knowledge_task_id=knowledge_task_id,
                    knowledge_filename=knowledge_filename,
                    promoted_at=promoted_at,
                )
            )
            db.commit()
            row = db.exec(
                select(AgentFeedback).where(col(AgentFeedback.feedback_id) == feedback_id)
            ).first()
            if row is None or not row.badcase_flag:
                return None
            return self._feedback_row_to_dict(row)

    @staticmethod
    def _feedback_row_to_dict(row: AgentFeedback) -> dict[str, Any]:
        return {
            "feedback_id": row.feedback_id,
            "run_id": row.run_id,
            "rating": row.rating,
            "comment": row.comment,
            "correction": row.correction,
            "badcase_flag": row.badcase_flag,
            "original_report": row.original_report,
            "review_status": row.review_status,
            "review_note": row.review_note,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at,
            "knowledge_status": row.knowledge_status,
            "knowledge_task_id": row.knowledge_task_id,
            "knowledge_filename": row.knowledge_filename,
            "promoted_at": row.promoted_at,
            "created_at": row.created_at,
        }


class AgentMemoryRepository:
    """Cross-session Agent memory repository."""

    def create_memory_with_session(
        self,
        db: Session,
        *,
        workspace_id: str,
        run_id: str | None,
        conclusion_text: str,
        conclusion_type: str = "final_report",
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        memory_id = str(uuid.uuid4())
        now = _utc_now()
        db.add(
            AgentMemory(
                memory_id=memory_id,
                workspace_id=workspace_id,
                run_id=run_id,
                conclusion_text=conclusion_text,
                conclusion_type=conclusion_type,
                confidence=confidence,
                validation_count=0,
                memory_metadata=metadata,
                created_at=now,
                updated_at=now,
            )
        )
        return memory_id

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
        with Session(bind=get_engine()) as db:
            memory_id = self.create_memory_with_session(
                db,
                workspace_id=workspace_id,
                run_id=run_id,
                conclusion_text=conclusion_text,
                conclusion_type=conclusion_type,
                confidence=confidence,
                metadata=metadata,
            )
            db.commit()
            return memory_id

    def search_memory(
        self,
        *,
        workspace_id: str,
        query: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as db:
            rows = db.exec(
                select(AgentMemory)
                .where(col(AgentMemory.workspace_id) == workspace_id)
                .order_by(col(AgentMemory.updated_at).desc())
                .limit(100)
            ).all()
        scored = [
            (score, self._row_to_dict(row))
            for row in rows
            if (score := _memory_text_score(query, row.conclusion_text)) > 0
        ]
        scored.sort(key=lambda item: (item[0], item[1]["confidence"]), reverse=True)
        return [{**item, "similarity": score} for score, item in scored[:limit]]

    @staticmethod
    def _row_to_dict(row: AgentMemory) -> dict[str, Any]:
        return {
            "memory_id": row.memory_id,
            "workspace_id": row.workspace_id,
            "run_id": row.run_id,
            "conclusion_text": row.conclusion_text,
            "conclusion_type": row.conclusion_type,
            "confidence": row.confidence,
            "validation_count": row.validation_count,
            "metadata": row.memory_metadata,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


def _memory_text_score(query: str, text: str) -> float:
    query_terms = _memory_terms(query)
    text_terms = _memory_terms(text)
    if not query_terms or not text_terms:
        return 0.0
    overlap = query_terms & text_terms
    if not overlap:
        return 0.0
    return round(len(overlap) / max(len(query_terms), 1), 4)


def _memory_terms(value: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in value)
    return {term for term in normalized.split() if len(term) >= 2}


workspace_repository = WorkspaceRepository()
knowledge_base_repository = KnowledgeBaseRepository()
scene_repository = SceneRepository()
tool_policy_repository = ToolPolicyRepository()
agent_run_repository = AgentRunRepository()
agent_feedback_repository = AgentFeedbackRepository()
agent_memory_repository = AgentMemoryRepository()
