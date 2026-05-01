"""Conversation and chat tool event repositories."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, col, select

from app.platform.persistence.database import get_engine
from app.platform.persistence.schema import ChatToolEvent, Message, Session as SessionModel


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
        now = _utc_now()
        with Session(bind=get_engine()) as db:
            existing = db.get(SessionModel, session_id)
            if existing is None:
                db.add(
                    SessionModel(
                        session_id=session_id,
                        title=title,
                        session_type=session_type,
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.commit()
                return

            if existing.title and existing.title != "新对话":
                title = existing.title
            existing.title = title
            existing.session_type = session_type
            existing.updated_at = now
            db.add(existing)
            db.commit()

    def append_message(self, session_id: str, role: str, content: str) -> None:
        now = _utc_now()
        with Session(bind=get_engine()) as db:
            db.add(
                Message(
                    session_id=session_id,
                    role=role,
                    content=content,
                    created_at=now,
                )
            )
            session_obj = db.get(SessionModel, session_id)
            if session_obj:
                session_obj.updated_at = now
                db.add(session_obj)
            db.commit()

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
        with Session(bind=get_engine()) as db:
            statement = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(col(Message.created_at).asc(), col(Message.id).asc())
            )
            rows = db.exec(statement).all()
        return [
            ConversationMessage(
                role=row.role,
                content=row.content,
                timestamp=row.created_at.isoformat()
                if isinstance(row.created_at, datetime)
                else str(row.created_at),
            )
            for row in rows
        ]

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all persisted sessions."""
        with Session(bind=get_engine()) as db:
            msg_count = (
                select(func.count())
                .where(col(Message.session_id) == col(SessionModel.session_id))
                .correlate(SessionModel)
                .scalar_subquery()
            )
            statement = select(
                SessionModel.session_id,
                SessionModel.title,
                SessionModel.session_type,
                SessionModel.created_at,
                SessionModel.updated_at,
                msg_count.label("message_count"),
            ).order_by(col(SessionModel.updated_at).desc())  # type: ignore[call-overload]
            rows = db.exec(statement).all()
        return [
            {
                "id": row.session_id,
                "title": row.title,
                "sessionType": row.session_type,
                "createdAt": row.created_at,
                "updatedAt": row.updated_at,
                "messageCount": row.message_count,
                "messages": [],
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        with Session(bind=get_engine()) as db:
            session_obj = db.get(SessionModel, session_id)
            if session_obj is None:
                return False
            db.delete(session_obj)
            db.commit()
        return True


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

        with Session(bind=get_engine()) as db:
            for event in events:
                db.add(
                    ChatToolEvent(
                        session_id=session_id,
                        exchange_id=exchange_id,
                        tool_name=str(event.get("toolName", "unknown")),
                        event_type=str(event.get("eventType", "call")),
                        payload=json.dumps(event.get("payload"), ensure_ascii=False)
                        if event.get("payload") is not None
                        else None,
                        created_at=_utc_now(),
                    )
                )
            db.commit()

    def list_events(self, session_id: str) -> list[dict[str, Any]]:
        """List session tool events chronologically."""
        with Session(bind=get_engine()) as db:
            statement = (
                select(ChatToolEvent)
                .where(ChatToolEvent.session_id == session_id)
                .order_by(col(ChatToolEvent.created_at).asc(), col(ChatToolEvent.id).asc())
            )
            rows = db.exec(statement).all()

        events: list[dict[str, Any]] = []
        for row in rows:
            payload = row.payload
            events.append(
                {
                    "id": row.id,
                    "sessionId": row.session_id,
                    "exchangeId": row.exchange_id,
                    "toolName": row.tool_name,
                    "eventType": row.event_type,
                    "payload": json.loads(payload) if payload else None,
                    "createdAt": row.created_at,
                }
            )
        return events


conversation_repository = ConversationRepository()
chat_tool_event_repository = ChatToolEventRepository()
