"""PostgreSQL database management."""

from __future__ import annotations

from collections.abc import Iterator

from loguru import logger
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session

from app.config import config

# ---------------------------------------------------------------------------
# SQLAlchemy engine
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        uri = config.sqlalchemy_database_uri
        if not uri:
            raise RuntimeError("POSTGRES_DSN must be configured")
        _engine = create_engine(
            uri,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency — yields a SQLModel Session."""
    session = Session(bind=get_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def health_check() -> bool:
    """Check database connectivity."""
    try:
        engine = get_engine()
        with engine.connect() as connection:
            row = connection.execute(text("SELECT 1 AS ok")).fetchone()
        if row is None:
            return False
        return bool(row[0] == 1)
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        return False
