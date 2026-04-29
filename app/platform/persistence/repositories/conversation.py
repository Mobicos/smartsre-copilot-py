"""Conversation and chat tool event repositories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.platform.persistence.database import database_manager


def utc_now() -> str:
    """Return an ISO 8601 UTC timestamp."""
    return datetime.now(UTC).isoformat()


def build_session_title(question: str) -> str:
    """Build a session title from the first user message."""
    compact = " ".join(question.split())
    return compact[:30] + ("..." if len(compact) > 30 else "") if compact else "新对话"


@dataclass
class ConversationMessage:
    """Persistent message view."""

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
    """Conversation and message repository."""

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
        """List all persisted sessions."""
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
    """Chat tool call event repository."""

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
        """List session tool events chronologically."""
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


conversation_repository = ConversationRepository()
chat_tool_event_repository = ChatToolEventRepository()
