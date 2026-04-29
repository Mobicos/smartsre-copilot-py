"""数据库 schema 常量。"""

SQLITE_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        session_type TEXT NOT NULL DEFAULT 'chat',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_messages_session_created_at
    ON messages(session_id, created_at, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS chat_tool_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT NOT NULL,
        exchange_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chat_tool_events_session_created
    ON chat_tool_events(session_id, created_at, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS aiops_runs (
        run_id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        status TEXT NOT NULL,
        task_input TEXT NOT NULL,
        report TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS aiops_run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        stage TEXT NOT NULL,
        message TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES aiops_runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_aiops_run_events_run_created
    ON aiops_run_events(run_id, created_at, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS indexing_tasks (
        task_id TEXT PRIMARY KEY,
        filename TEXT NOT NULL,
        file_path TEXT NOT NULL,
        status TEXT NOT NULL,
        attempt_count INTEGER NOT NULL DEFAULT 0,
        max_retries INTEGER NOT NULL DEFAULT 3,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        status_code INTEGER NOT NULL,
        subject TEXT,
        role TEXT,
        client_ip TEXT,
        user_agent TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_audit_logs_request_id
    ON audit_logs(request_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_checkpoints (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        checkpoint_type TEXT NOT NULL,
        checkpoint_data BLOB NOT NULL,
        metadata_type TEXT NOT NULL,
        metadata_data BLOB NOT NULL,
        parent_checkpoint_id TEXT,
        created_at TEXT NOT NULL,
        PRIMARY KEY(thread_id, checkpoint_ns, checkpoint_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_checkpoints_thread_created
    ON agent_checkpoints(thread_id, checkpoint_ns, checkpoint_id DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_checkpoint_blobs (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        channel TEXT NOT NULL,
        version TEXT NOT NULL,
        value_type TEXT NOT NULL,
        value_data BLOB NOT NULL,
        PRIMARY KEY(thread_id, checkpoint_ns, channel, version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_checkpoint_writes (
        thread_id TEXT NOT NULL,
        checkpoint_ns TEXT NOT NULL DEFAULT '',
        checkpoint_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        write_idx INTEGER NOT NULL,
        channel TEXT NOT NULL,
        value_type TEXT NOT NULL,
        value_data BLOB NOT NULL,
        task_path TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS workspaces (
        workspace_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_bases (
        knowledge_base_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        version TEXT NOT NULL DEFAULT '0.0.1',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scenes (
        scene_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        agent_config TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scene_knowledge_bases (
        scene_id TEXT NOT NULL,
        knowledge_base_id TEXT NOT NULL,
        PRIMARY KEY(scene_id, knowledge_base_id),
        FOREIGN KEY(scene_id) REFERENCES scenes(scene_id) ON DELETE CASCADE,
        FOREIGN KEY(knowledge_base_id) REFERENCES knowledge_bases(knowledge_base_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scene_tools (
        scene_id TEXT NOT NULL,
        tool_name TEXT NOT NULL,
        PRIMARY KEY(scene_id, tool_name),
        FOREIGN KEY(scene_id) REFERENCES scenes(scene_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tool_policies (
        tool_name TEXT PRIMARY KEY,
        scope TEXT NOT NULL DEFAULT 'diagnosis',
        risk_level TEXT NOT NULL DEFAULT 'low',
        capability TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        approval_required INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        run_id TEXT PRIMARY KEY,
        workspace_id TEXT NOT NULL,
        scene_id TEXT,
        session_id TEXT NOT NULL,
        status TEXT NOT NULL,
        goal TEXT NOT NULL,
        final_report TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(workspace_id) REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
        FOREIGN KEY(scene_id) REFERENCES scenes(scene_id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        stage TEXT NOT NULL,
        message TEXT NOT NULL,
        payload TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_agent_events_run_created
    ON agent_events(run_id, created_at, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS agent_feedback (
        feedback_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        rating TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE
    )
    """,
]


REQUIRED_TABLES = (
    "sessions",
    "messages",
    "chat_tool_events",
    "aiops_runs",
    "aiops_run_events",
    "indexing_tasks",
    "audit_logs",
    "agent_checkpoints",
    "agent_checkpoint_blobs",
    "agent_checkpoint_writes",
    "workspaces",
    "knowledge_bases",
    "scenes",
    "scene_knowledge_bases",
    "scene_tools",
    "tool_policies",
    "agent_runs",
    "agent_events",
    "agent_feedback",
)
