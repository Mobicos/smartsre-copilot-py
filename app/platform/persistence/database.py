"""PostgreSQL database management."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from loguru import logger
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import Pool, QueuePool
from sqlmodel import Session

from app.config import config

# ---------------------------------------------------------------------------
# SQLAlchemy engine
# ---------------------------------------------------------------------------

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None

_POOL_SIZE = 5
_POOL_MAX_OVERFLOW = 10
_POOL_WARN_THRESHOLD = 0.8


def _install_pool_listeners(pool: Pool) -> None:
    """Attach connection-pool monitoring events."""
    qpool = cast(QueuePool, pool)

    @event.listens_for(pool, "checkout")
    def _on_checkout(dbapi_conn, connection_record, connection_proxy):  # noqa: ARG001
        checked_out = qpool.checkedout()
        capacity = _POOL_SIZE + _POOL_MAX_OVERFLOW
        if checked_out >= capacity * _POOL_WARN_THRESHOLD:
            logger.warning(
                f"Database connection pool near capacity: "
                f"{checked_out}/{capacity} connections in use"
            )

    @event.listens_for(pool, "checkin")
    def _on_checkin(dbapi_conn, connection_record):  # noqa: ARG001
        pass


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        uri = config.sqlalchemy_database_uri
        if not uri:
            raise RuntimeError("POSTGRES_DSN must be configured")
        _engine = create_engine(
            uri,
            pool_size=_POOL_SIZE,
            max_overflow=_POOL_MAX_OVERFLOW,
            pool_pre_ping=True,
        )
        _install_pool_listeners(_engine.pool)
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


def get_pool_status() -> dict[str, int]:
    """Return current connection pool statistics."""
    engine = get_engine()
    pool = cast(QueuePool, engine.pool)
    return {
        "pool_size": pool.size(),
        "checked_out": pool.checkedout(),
        "checked_in": pool.checkedin(),
        "overflow": pool.overflow(),
    }
