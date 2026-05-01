from __future__ import annotations

from sqlalchemy import text

from app.platform.persistence import (
    aiops_run_repository,
    audit_log_repository,
    chat_tool_event_repository,
    conversation_repository,
)
from app.platform.persistence.database import get_engine


def test_conversation_repository_saves_lists_and_deletes_session():
    conversation_repository.save_chat_exchange(
        "session-1",
        "How do I debug high CPU?",
        "Check recent deploys and hot threads.",
    )

    sessions = conversation_repository.list_sessions()
    messages = conversation_repository.get_session_messages("session-1")

    assert len(sessions) == 1
    assert sessions[0]["id"] == "session-1"
    assert sessions[0]["messageCount"] == 2
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "How do I debug high CPU?"

    assert conversation_repository.delete_session("session-1")
    assert conversation_repository.get_session_messages("session-1") == []


def test_chat_tool_event_repository_persists_events_in_order():
    conversation_repository.ensure_session(
        "session-1",
        title="CPU 排查",
        session_type="chat",
    )
    chat_tool_event_repository.append_events(
        "session-1",
        exchange_id="exchange-1",
        events=[
            {
                "toolName": "retrieve_knowledge",
                "eventType": "call",
                "payload": {"toolCallId": "call-1", "args": {"query": "cpu"}},
            },
            {
                "toolName": "SearchLog",
                "eventType": "call",
                "payload": {"toolCallId": "call-2", "args": {"keyword": "error"}},
            },
        ],
    )

    events = chat_tool_event_repository.list_events("session-1")

    assert [event["toolName"] for event in events] == ["retrieve_knowledge", "SearchLog"]
    assert events[0]["exchangeId"] == "exchange-1"
    assert events[1]["payload"] == {"toolCallId": "call-2", "args": {"keyword": "error"}}


def test_aiops_run_repository_updates_status_and_report():
    run_id = aiops_run_repository.create_run("session-1", "diagnose alerts")

    aiops_run_repository.update_run(run_id, status="completed", report="root cause report")

    engine = get_engine()
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, report, error_message FROM aiops_runs")
        ).fetchone()

    assert row is not None
    assert row[0] == "completed"
    assert row[1] == "root cause report"
    assert row[2] is None


def test_aiops_run_repository_persists_events_in_order():
    run_id = aiops_run_repository.create_run("session-1", "diagnose alerts")

    aiops_run_repository.append_event(
        run_id,
        event_type="plan",
        stage="plan_created",
        message="计划已生成",
        payload={"steps": 2},
    )
    aiops_run_repository.append_event(
        run_id,
        event_type="report",
        stage="final_report",
        message="报告已生成",
        payload={"report": "root cause"},
    )

    events = aiops_run_repository.list_events(run_id)

    assert [event["type"] for event in events] == ["plan", "report"]
    assert events[0]["payload"] == {"steps": 2}
    assert events[1]["payload"] == {"report": "root cause"}


def test_audit_log_repository_persists_request_context():
    audit_log_repository.log_request(
        request_id="req-1",
        method="POST",
        path="/api/upload",
        status_code=202,
        subject="admin",
        role="admin",
        client_ip="127.0.0.1",
        user_agent="pytest",
    )

    engine = get_engine()
    with engine.connect() as connection:
        row = connection.execute(
            text("""
                SELECT request_id, method, path, status_code, subject, role, client_ip, user_agent
                FROM audit_logs
            """)
        ).fetchone()

    assert row is not None
    assert dict(row._mapping) == {
        "request_id": "req-1",
        "method": "POST",
        "path": "/api/upload",
        "status_code": 202,
        "subject": "admin",
        "role": "admin",
        "client_ip": "127.0.0.1",
        "user_agent": "pytest",
    }
