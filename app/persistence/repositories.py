"""应用持久化仓储。"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.persistence.database import database_manager


def utc_now() -> str:
    """返回 ISO 8601 UTC 时间戳。"""
    return datetime.now(UTC).isoformat()


def build_session_title(question: str) -> str:
    """根据首条用户消息构建标题。"""
    compact = " ".join(question.split())
    return compact[:30] + ("..." if len(compact) > 30 else "") if compact else "新对话"


@dataclass
class ConversationMessage:
    """持久化消息视图。"""

    role: str
    content: str
    timestamp: str

    def to_dict(self) -> dict[str, str]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }


class ConversationRepository:
    """会话与消息仓储。"""

    def ensure_session(
        self,
        session_id: str,
        *,
        title: str,
        session_type: str = "chat",
    ) -> None:
        database_manager.initialize()
        now = utc_now()
        with database_manager.get_connection() as connection:
            existing = connection.execute(
                "SELECT title, created_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO sessions (session_id, title, session_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, title, session_type, now, now),
                )
                return

            current_title = existing["title"]
            updated_title = current_title if current_title and current_title != "新对话" else title
            connection.execute(
                """
                UPDATE sessions
                SET title = ?, session_type = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (updated_title, session_type, now, session_id),
            )

    def append_message(self, session_id: str, role: str, content: str) -> None:
        database_manager.initialize()
        now = utc_now()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (session_id, role, content, now),
            )
            connection.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )

    def save_chat_exchange(self, session_id: str, question: str, answer: str) -> None:
        title = build_session_title(question)
        self.ensure_session(session_id, title=title, session_type="chat")
        self.append_message(session_id, "user", question)
        self.append_message(session_id, "assistant", answer)

    def save_aiops_report(self, session_id: str, prompt: str, report: str) -> None:
        title = build_session_title(prompt)
        self.ensure_session(session_id, title=title, session_type="aiops")
        self.append_message(session_id, "user", prompt)
        self.append_message(session_id, "assistant", report)

    def get_session_messages(self, session_id: str) -> list[ConversationMessage]:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        return [
            ConversationMessage(
                role=row["role"],
                content=row["content"],
                timestamp=row["created_at"],
            )
            for row in rows
        ]

    def list_sessions(self) -> list[dict[str, Any]]:
        """列出所有持久化会话。"""
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT
                    session_id,
                    title,
                    session_type,
                    created_at,
                    updated_at,
                    (
                        SELECT COUNT(1)
                        FROM messages
                        WHERE messages.session_id = sessions.session_id
                    ) AS message_count
                FROM sessions
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [
            {
                "id": row["session_id"],
                "title": row["title"],
                "sessionType": row["session_type"],
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
                "messageCount": row["message_count"],
                "messages": [],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            deleted = connection.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            ).rowcount
        return bool(deleted)


class AIOpsRunRepository:
    """AIOps 运行记录仓储。"""

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


class IndexingTaskRepository:
    """索引任务仓储。"""

    ACTIVE_TASK_STATUSES = ("queued", "processing")

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
        """查找指定文件当前活跃任务。"""
        database_manager.initialize()
        placeholders = ", ".join("?" for _ in self.ACTIVE_TASK_STATUSES)
        with database_manager.get_connection() as connection:
            row = connection.execute(
                f"""
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE file_path = ? AND status IN ({placeholders})
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (file_path, *self.ACTIVE_TASK_STATUSES),
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
        """领取指定任务。"""
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
        """按状态查询任务列表。"""
        database_manager.initialize()
        placeholders = ", ".join("?" for _ in statuses)
        with database_manager.get_connection() as connection:
            rows = connection.execute(
                f"""
                SELECT task_id, filename, file_path, status, attempt_count, max_retries,
                       error_message, created_at, updated_at
                FROM indexing_tasks
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC
                """,
                tuple(statuses),
            ).fetchall()
        return [dict(row) for row in rows]

    def claim_next_queued_task(self) -> dict[str, Any] | None:
        """原子地领取一个排队中的任务。"""
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
        """根据重试次数更新任务状态。"""
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
        """将超时未完成的 processing 任务重新入队。"""
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


class AuditLogRepository:
    """请求审计日志仓储。"""

    def log_request(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        status_code: int,
        subject: str | None,
        role: str | None,
        client_ip: str | None,
        user_agent: str | None,
        error_message: str | None = None,
    ) -> None:
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (
                    request_id, method, path, status_code, subject, role,
                    client_ip, user_agent, error_message, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    method,
                    path,
                    status_code,
                    subject,
                    role,
                    client_ip,
                    user_agent,
                    error_message,
                    utc_now(),
                ),
            )


conversation_repository = ConversationRepository()
aiops_run_repository = AIOpsRunRepository()
indexing_task_repository = IndexingTaskRepository()
audit_log_repository = AuditLogRepository()
