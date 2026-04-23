"""应用持久化仓储。"""

from __future__ import annotations

import json
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


class ChatToolEventRepository:
    """聊天工具调用事件仓储。"""

    def append_events(
        self,
        session_id: str,
        *,
        exchange_id: str,
        events: list[dict[str, Any]],
    ) -> None:
        if not events:
            return

        database_manager.initialize()
        with database_manager.get_connection() as connection:
            for event in events:
                connection.execute(
                    """
                    INSERT INTO chat_tool_events (
                        session_id, exchange_id, tool_name, event_type, payload, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        exchange_id,
                        str(event.get("toolName", "unknown")),
                        str(event.get("eventType", "call")),
                        json.dumps(event.get("payload"), ensure_ascii=False)
                        if event.get("payload") is not None
                        else None,
                        utc_now(),
                    ),
                )

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        """按时间顺序列出会话工具事件。"""
        database_manager.initialize()
        with database_manager.get_connection() as connection:
            rows = connection.execute(
                """
                SELECT id, session_id, exchange_id, tool_name, event_type, payload, created_at
                FROM chat_tool_events
                WHERE session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()

        events: list[dict[str, Any]] = []
        for row in rows:
            payload = row["payload"]
            events.append(
                {
                    "id": row["id"],
                    "sessionId": row["session_id"],
                    "exchangeId": row["exchange_id"],
                    "toolName": row["tool_name"],
                    "eventType": row["event_type"],
                    "payload": json.loads(payload) if payload else None,
                    "createdAt": row["created_at"],
                }
            )
        return events


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

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """获取单次 AIOps 运行记录。"""
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
        """追加 AIOps 中间事件。"""
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
        """按时间顺序列出运行事件。"""
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


class IndexingTaskRepository:
    """索引任务仓储。"""

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
        """查找指定文件当前活跃任务。"""
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
chat_tool_event_repository = ChatToolEventRepository()
aiops_run_repository = AIOpsRunRepository()
indexing_task_repository = IndexingTaskRepository()
audit_log_repository = AuditLogRepository()
