"""LangGraph checkpoint persistence backed by the application database."""

from __future__ import annotations

import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    get_checkpoint_id,
    get_checkpoint_metadata,
)

from app.platform.persistence.database import DatabaseManager, database_manager


class DatabaseCheckpointSaver(BaseCheckpointSaver[str]):
    """Persist LangGraph checkpoints in SQLite/PostgreSQL."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__()
        self._db_manager = db_manager

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        requested_checkpoint_id = get_checkpoint_id(config)

        with self._db_manager.get_connection() as connection:
            if requested_checkpoint_id:
                row = connection.fetchone(
                    """
                    SELECT checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data,
                           parent_checkpoint_id
                    FROM agent_checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                    """,
                    (thread_id, checkpoint_ns, requested_checkpoint_id),
                )
            else:
                row = connection.fetchone(
                    """
                    SELECT checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data,
                           parent_checkpoint_id
                    FROM agent_checkpoints
                    WHERE thread_id = ? AND checkpoint_ns = ?
                    ORDER BY checkpoint_id DESC
                    LIMIT 1
                    """,
                    (thread_id, checkpoint_ns),
                )

            if row is None:
                return None

            checkpoint_id = str(row["checkpoint_id"])
            writes = connection.fetchall(
                """
                SELECT task_id, channel, value_type, value_data, task_path
                FROM agent_checkpoint_writes
                WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                ORDER BY write_idx ASC
                """,
                (thread_id, checkpoint_ns, checkpoint_id),
            )

        checkpoint = self._deserialize_typed(
            str(row["checkpoint_type"]),
            bytes(row["checkpoint_data"]),
        )
        metadata = self._deserialize_typed(
            str(row["metadata_type"]),
            bytes(row["metadata_data"]),
        )

        if not isinstance(checkpoint, dict):
            return None
        if not isinstance(metadata, dict):
            metadata = {}

        checkpoint_data = cast(Checkpoint, dict(checkpoint))
        checkpoint_data["channel_values"] = self._load_blobs(
            thread_id,
            checkpoint_ns,
            checkpoint_data["channel_versions"],
        )

        parent_checkpoint_id = row["parent_checkpoint_id"]

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=checkpoint_data,
            metadata=cast(CheckpointMetadata, metadata),
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": str(parent_checkpoint_id),
                    }
                }
                if parent_checkpoint_id
                else None
            ),
            pending_writes=[
                (
                    str(write["task_id"]),
                    str(write["channel"]),
                    self._deserialize_typed(
                        str(write["value_type"]),
                        bytes(write["value_data"]),
                    ),
                )
                for write in writes
            ],
        )

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        thread_id = str(config["configurable"]["thread_id"]) if config else None
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", "")) if config else None
        checkpoint_id = get_checkpoint_id(config) if config else None
        before_checkpoint_id = get_checkpoint_id(before) if before else None

        query = """
            SELECT thread_id, checkpoint_ns, checkpoint_id
            FROM agent_checkpoints
        """
        conditions: list[str] = []
        params: list[Any] = []

        if thread_id is not None:
            conditions.append("thread_id = ?")
            params.append(thread_id)
        if checkpoint_ns is not None:
            conditions.append("checkpoint_ns = ?")
            params.append(checkpoint_ns)
        if checkpoint_id is not None:
            conditions.append("checkpoint_id = ?")
            params.append(checkpoint_id)
        if before_checkpoint_id is not None:
            conditions.append("checkpoint_id < ?")
            params.append(before_checkpoint_id)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY checkpoint_id DESC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        with self._db_manager.get_connection() as connection:
            rows = connection.fetchall(query, params)

        for row in rows:
            tuple_config = {
                "configurable": {
                    "thread_id": str(row["thread_id"]),
                    "checkpoint_ns": str(row["checkpoint_ns"]),
                    "checkpoint_id": str(row["checkpoint_id"]),
                }
            }
            checkpoint_tuple = self.get_tuple(cast(RunnableConfig, tuple_config))
            if checkpoint_tuple is None:
                continue
            if filter and not all(
                checkpoint_tuple.metadata.get(key) == value for key, value in filter.items()
            ):
                continue
            yield checkpoint_tuple

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(checkpoint["id"])
        checkpoint_copy = checkpoint.copy()
        values: dict[str, Any] = checkpoint_copy.pop("channel_values")  # type: ignore[misc]
        checkpoint_type, checkpoint_data = self.serde.dumps_typed(checkpoint_copy)
        metadata_type, metadata_data = self.serde.dumps_typed(
            get_checkpoint_metadata(config, metadata)
        )

        with self._db_manager.get_connection() as connection:
            for channel, version in new_versions.items():
                value_type, value_data = (
                    self.serde.dumps_typed(values[channel]) if channel in values else ("empty", b"")
                )
                connection.execute(
                    """
                    INSERT INTO agent_checkpoint_blobs (
                        thread_id, checkpoint_ns, channel, version, value_type, value_data
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(thread_id, checkpoint_ns, channel, version)
                    DO UPDATE SET
                        value_type = excluded.value_type,
                        value_data = excluded.value_data
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        str(channel),
                        str(version),
                        value_type,
                        value_data,
                    ),
                )

            connection.execute(
                """
                INSERT INTO agent_checkpoints (
                    thread_id, checkpoint_ns, checkpoint_id, checkpoint_type, checkpoint_data,
                    metadata_type, metadata_data, parent_checkpoint_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(thread_id, checkpoint_ns, checkpoint_id)
                DO UPDATE SET
                    checkpoint_type = excluded.checkpoint_type,
                    checkpoint_data = excluded.checkpoint_data,
                    metadata_type = excluded.metadata_type,
                    metadata_data = excluded.metadata_data,
                    parent_checkpoint_id = excluded.parent_checkpoint_id,
                    created_at = excluded.created_at
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    checkpoint_type,
                    checkpoint_data,
                    metadata_type,
                    metadata_data,
                    config["configurable"].get("checkpoint_id"),
                    checkpoint["ts"],
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        checkpoint_id = str(config["configurable"]["checkpoint_id"])

        with self._db_manager.get_connection() as connection:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                existing = connection.fetchone(
                    """
                    SELECT 1 AS exists_flag
                    FROM agent_checkpoint_writes
                    WHERE thread_id = ? AND checkpoint_ns = ? AND checkpoint_id = ?
                      AND task_id = ? AND write_idx = ?
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        write_idx,
                    ),
                )
                if write_idx >= 0 and existing is not None:
                    continue

                value_type, value_data = self.serde.dumps_typed(value)
                connection.execute(
                    """
                    INSERT INTO agent_checkpoint_writes (
                        thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx,
                        channel, value_type, value_data, task_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                    DO UPDATE SET
                        channel = excluded.channel,
                        value_type = excluded.value_type,
                        value_data = excluded.value_data,
                        task_path = excluded.task_path
                    """,
                    (
                        thread_id,
                        checkpoint_ns,
                        checkpoint_id,
                        task_id,
                        write_idx,
                        channel,
                        value_type,
                        value_data,
                        task_path,
                    ),
                )

    def delete_thread(self, thread_id: str) -> None:
        with self._db_manager.get_connection() as connection:
            connection.execute(
                "DELETE FROM agent_checkpoint_writes WHERE thread_id = ?",
                (thread_id,),
            )
            connection.execute(
                "DELETE FROM agent_checkpoint_blobs WHERE thread_id = ?",
                (thread_id,),
            )
            connection.execute(
                "DELETE FROM agent_checkpoints WHERE thread_id = ?",
                (thread_id,),
            )

    def delete_namespace(self, thread_id: str, checkpoint_ns: str) -> None:
        with self._db_manager.get_connection() as connection:
            connection.execute(
                """
                DELETE FROM agent_checkpoint_writes
                WHERE thread_id = ? AND checkpoint_ns = ?
                """,
                (thread_id, checkpoint_ns),
            )
            connection.execute(
                """
                DELETE FROM agent_checkpoint_blobs
                WHERE thread_id = ? AND checkpoint_ns = ?
                """,
                (thread_id, checkpoint_ns),
            )
            connection.execute(
                """
                DELETE FROM agent_checkpoints
                WHERE thread_id = ? AND checkpoint_ns = ?
                """,
                (thread_id, checkpoint_ns),
            )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return self.get_tuple(config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return self.put(config, checkpoint, metadata, new_versions)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self.put_writes(config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        self.delete_thread(thread_id)

    def get_next_version(self, current: str | None, channel: None) -> str:
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        next_v = current_v + 1
        next_h = random.random()
        return f"{next_v:032}.{next_h:016}"

    def _load_blobs(
        self,
        thread_id: str,
        checkpoint_ns: str,
        versions: ChannelVersions,
    ) -> dict[str, Any]:
        if not versions:
            return {}

        channel_values: dict[str, Any] = {}
        with self._db_manager.get_connection() as connection:
            for channel, version in versions.items():
                row = connection.fetchone(
                    """
                    SELECT value_type, value_data
                    FROM agent_checkpoint_blobs
                    WHERE thread_id = ? AND checkpoint_ns = ? AND channel = ? AND version = ?
                    """,
                    (thread_id, checkpoint_ns, str(channel), str(version)),
                )
                if row is None or row["value_type"] == "empty":
                    continue
                channel_values[str(channel)] = self._deserialize_typed(
                    str(row["value_type"]),
                    bytes(row["value_data"]),
                )
        return channel_values

    def _deserialize_typed(self, value_type: str, value_data: bytes) -> Any:
        return self.serde.loads_typed((value_type, value_data))


checkpoint_saver = DatabaseCheckpointSaver(database_manager)
