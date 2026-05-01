"""Indexing task repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import IndexingTask


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _model_to_dict(obj: Any) -> dict[str, Any]:
    return {k: v for k, v in obj.__dict__.items() if k != "_sa_instance_state"}


class IndexingTaskRepository:
    """Indexing task repository."""

    ACTIVE_TASK_STATUSES = ("queued", "processing")
    ALLOWED_TASK_STATUSES = frozenset(
        {
            "queued",
            "processing",
            "completed",
            "failed_permanently",
        }
    )

    def create_task(
        self,
        filename: str,
        file_path: str,
        *,
        max_retries: int,
    ) -> str:
        task_id = str(uuid.uuid4())
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            task = IndexingTask(
                task_id=task_id,
                filename=filename,
                file_path=file_path,
                status="queued",
                attempt_count=0,
                max_retries=max_retries,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.commit()
        return task_id

    def find_active_task_by_file_path(self, file_path: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            statement = (
                select(IndexingTask)
                .where(IndexingTask.file_path == file_path)
                .where(col(IndexingTask.status).in_(self.ACTIVE_TASK_STATUSES))
                .order_by(col(IndexingTask.created_at).desc())
                .limit(1)
            )
            row = session.exec(statement).first()
        return _model_to_dict(row) if row else None

    def update_task(
        self,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        with Session(bind=get_engine()) as session:
            task = session.get(IndexingTask, task_id)
            if task is None:
                return
            task.status = status
            task.error_message = error_message
            task.updated_at = _utc_now()
            session.add(task)
            session.commit()

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            task = session.get(IndexingTask, task_id)
        return _model_to_dict(task) if task else None

    def claim_task(self, task_id: str) -> dict[str, Any] | None:
        """Claim a queued task."""
        now = _utc_now()
        with Session(bind=get_engine()) as session:
            stmt = (
                sa.update(IndexingTask)
                .where(col(IndexingTask.task_id) == task_id, col(IndexingTask.status) == "queued")
                .values(
                    status="processing",
                    updated_at=now,
                    error_message=None,
                    attempt_count=IndexingTask.attempt_count + 1,
                )
            )
            result = session.exec(stmt)
            if result.rowcount == 0:
                session.commit()
                return None
            session.commit()
            task = session.get(IndexingTask, task_id)
        return _model_to_dict(task) if task else None

    def list_tasks_by_status(self, statuses: list[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []

        invalid_statuses = [s for s in statuses if s not in self.ALLOWED_TASK_STATUSES]
        if invalid_statuses:
            raise ValueError(f"Unsupported task statuses: {', '.join(invalid_statuses)}")

        normalized_statuses = list(dict.fromkeys(statuses))
        with Session(bind=get_engine()) as session:
            statement = (
                select(IndexingTask)
                .where(col(IndexingTask.status).in_(normalized_statuses))
                .order_by(col(IndexingTask.created_at).asc())
            )
            rows = session.exec(statement).all()
        return [_model_to_dict(row) for row in rows]

    def claim_next_queued_task(self) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            statement = (
                select(IndexingTask)
                .where(IndexingTask.status == "queued")
                .order_by(col(IndexingTask.created_at).asc())
                .limit(1)
            )
            row = session.exec(statement).first()
        if row is None:
            return None
        return self.claim_task(row.task_id)

    def mark_retry_or_failed(self, task_id: str, error_message: str) -> dict[str, Any] | None:
        with Session(bind=get_engine()) as session:
            task = session.get(IndexingTask, task_id)
            if task is None:
                return None
            next_status = (
                "failed_permanently" if task.attempt_count >= task.max_retries else "queued"
            )
            task.status = next_status
            task.error_message = error_message
            task.updated_at = _utc_now()
            session.add(task)
            session.commit()
            session.refresh(task)
            return _model_to_dict(task)

    def requeue_stale_processing_tasks(self, timeout_seconds: int) -> int:
        threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        requeued = 0
        with Session(bind=get_engine()) as session:
            statement = select(IndexingTask).where(IndexingTask.status == "processing")
            rows = session.exec(statement).all()

            for row in rows:
                if row.updated_at <= threshold:
                    next_status = (
                        "failed_permanently" if row.attempt_count >= row.max_retries else "queued"
                    )
                    row.status = next_status
                    row.updated_at = _utc_now()
                    row.error_message = (
                        "Task requeued after worker timeout"
                        if next_status == "queued"
                        else "Task exceeded retry limit after worker timeout"
                    )
                    session.add(row)
                    requeued += 1

            session.commit()
        return requeued


indexing_task_repository = IndexingTaskRepository()
