"""Chat application orchestration."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

from app.persistence.repositories import ChatToolEventRepository, ConversationRepository
from app.services.rag_agent_service import RagAgentService


class ChatApplicationService:
    """Coordinate chat runtime and persistence."""

    def __init__(
        self,
        *,
        rag_agent_service: RagAgentService,
        conversation_repository: ConversationRepository,
        chat_tool_event_repository: ChatToolEventRepository,
    ) -> None:
        self._rag_agent_service = rag_agent_service
        self._conversation_repository = conversation_repository
        self._chat_tool_event_repository = chat_tool_event_repository

    async def run_chat(self, session_id: str, question: str) -> dict[str, Any]:
        """Execute a non-streaming chat exchange and persist side effects."""
        exchange_id = str(uuid.uuid4())
        result = await self._rag_agent_service.query(question, session_id=session_id)
        self._conversation_repository.save_chat_exchange(session_id, question, result.answer)
        self._chat_tool_event_repository.append_events(
            session_id,
            exchange_id=exchange_id,
            events=result.tool_events,
        )
        return {
            "exchangeId": exchange_id,
            "answer": result.answer,
            "toolEvents": result.tool_events,
        }

    async def stream_chat(
        self,
        session_id: str,
        question: str,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Execute a streaming chat exchange and persist on completion."""
        exchange_id = str(uuid.uuid4())
        full_response = ""
        tool_events: list[dict[str, Any]] = []

        async for chunk in self._rag_agent_service.query_stream(question, session_id=session_id):
            chunk_type = chunk.get("type", "unknown")
            chunk_data = chunk.get("data")

            if chunk_type == "debug":
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "type": "debug",
                            "node": chunk.get("node", "unknown"),
                            "message_type": chunk.get("message_type", "unknown"),
                        },
                        ensure_ascii=False,
                    ),
                }
                continue

            if chunk_type == "tool_call":
                if isinstance(chunk_data, dict):
                    tool_events.append(chunk_data)
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {"type": "tool_call", "data": chunk_data},
                        ensure_ascii=False,
                    ),
                }
                continue

            if chunk_type == "search_results":
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {"type": "search_results", "data": chunk_data},
                        ensure_ascii=False,
                    ),
                }
                continue

            if chunk_type == "content":
                full_response += str(chunk_data or "")
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {"type": "content", "data": chunk_data},
                        ensure_ascii=False,
                    ),
                }
                continue

            if chunk_type == "complete":
                complete_data = chunk_data if isinstance(chunk_data, dict) else {}
                if not full_response:
                    full_response = str(complete_data.get("answer", ""))
                complete_tool_calls = complete_data.get("tool_calls", [])
                if isinstance(complete_tool_calls, list):
                    tool_events = cast(list[dict[str, Any]], complete_tool_calls)

                self._conversation_repository.save_chat_exchange(
                    session_id,
                    question,
                    full_response,
                )
                self._chat_tool_event_repository.append_events(
                    session_id,
                    exchange_id=exchange_id,
                    events=tool_events,
                )
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {
                            "type": "done",
                            "data": {
                                "exchangeId": exchange_id,
                                "answer": full_response,
                                "tool_calls": tool_events,
                            },
                        },
                        ensure_ascii=False,
                    ),
                }
                continue

            if chunk_type == "error":
                yield {
                    "event": "message",
                    "data": json.dumps(
                        {"type": "error", "data": str(chunk_data)},
                        ensure_ascii=False,
                    ),
                }

    def clear_session(self, session_id: str) -> bool:
        """Clear persisted and checkpoint-backed session history."""
        runtime_deleted = self._rag_agent_service.clear_session(session_id)
        persistent_deleted = self._conversation_repository.delete_session(session_id)
        return runtime_deleted or persistent_deleted
