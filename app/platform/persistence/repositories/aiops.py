"""AIOps run and event repositories."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import AIOpsRun, AIOpsRunEvent


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}


class AIOpsRunRepository:
    """AIOps run repository."""

    def create_run(self, session_id: str, task_input: str) -> str:
        run_id = str(uuid.uuid4())
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            run = AIOpsRun(
                run_id=run_id,
                session_id=session_id,
                status="running",
                task_input=task_input,
                created_at=now,
                updated_at=now,
            )
            session.add(run)
            session.commit()
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        with Session(bind=get_engine()) as session:
            run = session.get(AIOpsRun, run_id)
            if run is None:
                return
            run.status = status
            if report is not None:
                run.report = report
            if error_message is not None:
                run.error_message = error_message
            run.updated_at = _utc_now()
            session.add(run)
            session.commit()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            run = session.get(AIOpsRun, run_id)
            return _model_to_dict(run) if run else None

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
            event = AIOpsRunEvent(
                run_id=run_id,
                event_type=event_type,
                stage=stage,
                message=message,
                payload=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                created_at=_utc_now(),
            )
            session.add(event)
            session.commit()

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        with Session(bind=get_engine()) as session:
            statement = (
                select(AIOpsRunEvent)
                .where(AIOpsRunEvent.run_id == run_id)
                .order_by(col(AIOpsRunEvent.created_at).asc(), col(AIOpsRunEvent.id).asc())
            )
            rows = session.exec(statement).all()
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = row.payload
            events.append(
                {
                    "id": row.id,
                    "runId": row.run_id,
                    "type": row.event_type,
                    "stage": row.stage,
                    "message": row.message,
                    "payload": json.loads(payload) if payload else None,
                    "createdAt": row.created_at,
                }
            )
        return events


aiops_run_repository = AIOpsRunRepository()
