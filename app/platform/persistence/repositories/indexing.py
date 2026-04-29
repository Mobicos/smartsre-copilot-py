"""Indexing task repository."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.platform.persistence.database import database_manager


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


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
        database_manager.initialize()
        task_id = str(uuid.uuid4())
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO indexing_tasks (
                    task_id, filename, file_path, status, attempt_count, max_retries,
                    error_message, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (task_id, filename, file_path, "queued", 0, max_retries, None, now, now),
            )
        return task_id

    def find_active_task_by_file_path(self, file_path: str) -> dict[str, Any] | None:
        """Find the active task for a file path."""
        database_manager.initialize()
        status_queued, status_processing = self.ACTIVE_TASK_STATUSES
        with database_manager.get_connection() as connection:
            row = connection.execute(
                """
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE file_path = ? AND status IN (?, ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (file_path, status_queued, status_processing),
            ).fetchone()
        return dict(row) if row is not None else None

    def update_task(
        self,
        task_id: str,
        *,
        status: str,
        error_message: str | None = None,
    ) -> None:
        database_manager.initialize()
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                UPDATE indexing_tasks
                SET status = ?, error_message = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (status, error_message, now, task_id),
            )

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.execute(
                """
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def claim_task(self, task_id: str) -> dict[str, Any] | None:
        """Claim a queued task."""
        database_manager.initialize()
        now = utc_now()
        with database_manager.get_connection() as connection:
            cursor = connection.execute(
                """
                UPDATE indexing_tasks
                SET status = 'processing', updated_at = ?, error_message = NULL, attempt_count = attempt_count + 1
                WHERE task_id = ? AND status = 'queued'
                """,
                (now, task_id),
            )
            if getattr(cursor, "rowcount", 0) == 0:
                return None

            row = connection.fetchone(
                """
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            )
        return dict(row) if row is not None else None

    def list_tasks_by_status(self, statuses: list[str]) -> list[dict[str, Any]]:
        """List tasks by status."""
        database_manager.initialize()
        if not statuses:
            return []

        invalid_statuses = [
            status for status in statuses if status not in self.ALLOWED_TASK_STATUSES
        ]
        if invalid_statuses:
            raise ValueError(f"Unsupported task statuses: {', '.join(invalid_statuses)}")

        normalized_statuses = list(dict.fromkeys(statuses))
        query = """
            SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                   error_message, created_at, updated_at
            FROM indexing_tasks
            WHERE status = ?
            ORDER BY created_at ASC
        """
        rows: list[Any] = []
        with database_manager.get_connection() as connection:
            for status in normalized_statuses:
                rows.extend(connection.execute(query, (status,)).fetchall())

        rows.sort(key=lambda row: row["created_at"])
        return [dict(row) for row in rows]

    def claim_next_queued_task(self) -> dict[str, Any] | None:
        """Atomically claim the next queued task."""
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            row = connection.fetchone(
                """
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE status = 'queued'
                ORDER BY created_at ASC
                LIMIT 1
                """
            )
        if row is None:
            return None
        return self.claim_task(row["task_id"])

    def mark_retry_or_failed(self, task_id: str, error_message: str) -> dict[str, Any] | None:
        """Update task status based on retry count."""
        database_manager.initialize()
        now = utc_now()
        with database_manager.get_connection() as connection:
            row = connection.execute(
                """
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                return None

            next_status = (
                "failed_permanently" if row["attempt_count"] >= row["max_retries"] else "queued"
            )
            connection.execute(
                """
                UPDATE indexing_tasks
                SET status = ?, error_message = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (next_status, error_message, now, task_id),
            )
            updated_row = connection.execute(
                """
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(updated_row) if updated_row is not None else None

    def requeue_stale_processing_tasks(self, timeout_seconds: int) -> int:
        """Requeue stale processing tasks."""
        database_manager.initialize()
        threshold = datetime.now(UTC) - timedelta(seconds=timeout_seconds)
        requeued = 0
        with database_manager.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT task_id, updated_at, attempt_count, max_retries
                FROM indexing_tasks
                WHERE status = 'processing'
                """
            ).fetchall()

            for row in rows:
                updated_at = datetime.fromisoformat(row["updated_at"])
                if updated_at <= threshold:
                    next_status = (
                        "failed_permanently"
                        if row["attempt_count"] >= row["max_retries"]
                        else "queued"
                    )
                    connection.execute(
                        """
                        UPDATE indexing_tasks
                        SET status = ?, updated_at = ?, error_message = ?
                        WHERE task_id = ?
                        """,
                        (
                            next_status,
                            utc_now(),
                            "Task requeued after worker timeout"
                            if next_status == "queued"
                            else "Task exceeded retry limit after worker timeout",
                            row["task_id"],
                        ),
                    )
                    requeued += 1

        return requeued


indexing_task_repository = IndexingTaskRepository()
