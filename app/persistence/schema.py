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
]


REQUIRED_TABLES = (
    "sessions",
    "messages",
    "aiops_runs",
    "indexing_tasks",
    "audit_logs",
)
