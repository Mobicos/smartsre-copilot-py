"""AIOps run and event repositories."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.platform.persistence.database import database_manager


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


class AIOpsRunRepository:
    """AIOps run repository."""

    def create_run(self, session_id: str, task_input: str) -> str:
        database_manager.initialize()
        run_id = str(uuid.uuid4())
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO aiops_runs (
                    run_id, session_id, status, task_input, report, error_message, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (run_id, session_id, "running", task_input, None, None, now, now),
            )
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        status: str,
        report: str | None = None,
        error_message: str | None = None,
    ) -> None:
        database_manager.initialize()
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                UPDATE aiops_runs
                SET status = ?, report = COALESCE(?, report), error_message = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (status, report, error_message, now, run_id),
            )

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get an AIOps run record."""
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.execute(
                """
                SELECT run_id, session_id, status, task_input, report, error_message, created_at, updated_at
                FROM aiops_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def append_event(
        self,
        run_id: str,
        *,
        event_type: str,
        stage: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append an AIOps runtime event."""
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO aiops_run_events (
                    run_id, event_type, stage, message, payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_type,
                    stage,
                    message,
                    json.dumps(payload, ensure_ascii=False) if payload is not None else None,
                    utc_now(),
                ),
            )

    def list_events(self, run_id: str) -> list[dict[str, Any]]:
        """List run events chronologically."""
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, run_id, event_type, stage, message, payload, created_at
                FROM aiops_run_events
                WHERE run_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (run_id,),
            ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            payload = row["payload"]
            events.append(
                {
                    "id": row["id"],
                    "runId": row["run_id"],
                    "type": row["event_type"],
                    "stage": row["stage"],
                    "message": row["message"],
                    "payload": json.loads(payload) if payload else None,
                    "createdAt": row["created_at"],
                }
            )
        return events


aiops_run_repository = AIOpsRunRepository()
