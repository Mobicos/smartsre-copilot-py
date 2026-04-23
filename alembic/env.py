"""Alembic environment configuration."""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _resolve_database_url() -> str:
    backend = os.getenv("DATABASE_BACKEND", "postgres").strip().lower()
    if backend == "sqlite":
        database_path = os.getenv("DATABASE_PATH", "data/smartsre_copilot.db")
        return f"sqlite:///{database_path}"

    return os.getenv(
        "POSTGRES_DSN",
        config.get_main_option("sqlalchemy.url"),
    )


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode."""
    connectable = create_engine(
        _resolve_database_url(),
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
