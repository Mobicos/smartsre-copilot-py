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
from sqlalchemy import text

from app.platform.persistence.database import get_engine


class DatabaseCheckpointSaver(BaseCheckpointSaver[str]):
    """Persist LangGraph checkpoints in PostgreSQL."""

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id = str(config["configurable"]["thread_id"])
        checkpoint_ns = str(config["configurable"].get("checkpoint_ns", ""))
        requested_checkpoint_id = get_checkpoint_id(config)

        engine = get_engine()
        with engine.connect() as connection:
            if requested_checkpoint_id:
                row = connection.execute(
                    text("""
                        SELECT checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data,
                               parent_checkpoint_id
                        FROM agent_checkpoints
                        WHERE thread_id = :tid AND checkpoint_ns = :ns AND checkpoint_id = :cid
                    """),
                    {"tid": thread_id, "ns": checkpoint_ns, "cid": requested_checkpoint_id},
                ).fetchone()
            else:
                row = connection.execute(
                    text("""
                        SELECT checkpoint_id, checkpoint_type, checkpoint_data, metadata_type, metadata_data,
                               parent_checkpoint_id
                        FROM agent_checkpoints
                        WHERE thread_id = :tid AND checkpoint_ns = :ns
                        ORDER BY checkpoint_id DESC
                        LIMIT 1
                    """),
                    {"tid": thread_id, "ns": checkpoint_ns},
                ).fetchone()

            if row is None:
                return None

            checkpoint_id = str(row[0])
            writes = connection.execute(
                text("""
                    SELECT task_id, channel, value_type, value_data, task_path
                    FROM agent_checkpoint_writes
                    WHERE thread_id = :tid AND checkpoint_ns = :ns AND checkpoint_id = :cid
                    ORDER BY write_idx ASC
                """),
                {"tid": thread_id, "ns": checkpoint_ns, "cid": checkpoint_id},
            ).fetchall()

        checkpoint = self._deserialize_typed(
            str(row[1]),
            bytes(row[2]),
        )
        metadata = self._deserialize_typed(
            str(row[3]),
            bytes(row[4]),
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

        parent_checkpoint_id = row[5]

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
                    str(write[0]),
                    str(write[1]),
                    self._deserialize_typed(
                        str(write[2]),
                        bytes(write[3]),
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
        params: dict[str, Any] = {}

        if thread_id is not None:
            conditions.append("thread_id = :tid")
            params["tid"] = thread_id
        if checkpoint_ns is not None:
            conditions.append("checkpoint_ns = :ns")
            params["ns"] = checkpoint_ns
        if checkpoint_id is not None:
            conditions.append("checkpoint_id = :cid")
            params["cid"] = checkpoint_id
        if before_checkpoint_id is not None:
            conditions.append("checkpoint_id < :bcid")
            params["bcid"] = before_checkpoint_id

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY checkpoint_id DESC"
        if limit is not None:
            query += f" LIMIT {int(limit)}"

        engine = get_engine()
        with engine.connect() as connection:
            rows = connection.execute(text(query), params).fetchall()

        for row in rows:
            tuple_config = {
                "configurable": {
                    "thread_id": str(row[0]),
                    "checkpoint_ns": str(row[1]),
                    "checkpoint_id": str(row[2]),
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

        engine = get_engine()
        with engine.begin() as connection:
            for channel, version in new_versions.items():
                value_type, value_data = (
                    self.serde.dumps_typed(values[channel]) if channel in values else ("empty", b"")
                )
                connection.execute(
                    text("""
                        INSERT INTO agent_checkpoint_blobs (
                            thread_id, checkpoint_ns, channel, version, value_type, value_data
                        ) VALUES (:tid, :ns, :ch, :ver, :vt, :vd)
                        ON CONFLICT(thread_id, checkpoint_ns, channel, version)
                        DO UPDATE SET
                            value_type = excluded.value_type,
                            value_data = excluded.value_data
                    """),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "ch": str(channel),
                        "ver": str(version),
                        "vt": value_type,
                        "vd": value_data,
                    },
                )

            connection.execute(
                text("""
                    INSERT INTO agent_checkpoints (
                        thread_id, checkpoint_ns, checkpoint_id, checkpoint_type, checkpoint_data,
                        metadata_type, metadata_data, parent_checkpoint_id, created_at
                    ) VALUES (:tid, :ns, :cid, :ct, :cd, :mt, :md, :pcid, :ts)
                    ON CONFLICT(thread_id, checkpoint_ns, checkpoint_id)
                    DO UPDATE SET
                        checkpoint_type = excluded.checkpoint_type,
                        checkpoint_data = excluded.checkpoint_data,
                        metadata_type = excluded.metadata_type,
                        metadata_data = excluded.metadata_data,
                        parent_checkpoint_id = excluded.parent_checkpoint_id,
                        created_at = excluded.created_at
                """),
                {
                    "tid": thread_id,
                    "ns": checkpoint_ns,
                    "cid": checkpoint_id,
                    "ct": checkpoint_type,
                    "cd": checkpoint_data,
                    "mt": metadata_type,
                    "md": metadata_data,
                    "pcid": config["configurable"].get("checkpoint_id"),
                    "ts": checkpoint["ts"],
                },
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

        engine = get_engine()
        with engine.begin() as connection:
            for idx, (channel, value) in enumerate(writes):
                write_idx = WRITES_IDX_MAP.get(channel, idx)
                existing = connection.execute(
                    text("""
                        SELECT 1 AS exists_flag
                        FROM agent_checkpoint_writes
                        WHERE thread_id = :tid AND checkpoint_ns = :ns AND checkpoint_id = :cid
                          AND task_id = :task_id AND write_idx = :wi
                    """),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "cid": checkpoint_id,
                        "task_id": task_id,
                        "wi": write_idx,
                    },
                ).fetchone()
                if write_idx >= 0 and existing is not None:
                    continue

                value_type, value_data = self.serde.dumps_typed(value)
                connection.execute(
                    text("""
                        INSERT INTO agent_checkpoint_writes (
                            thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx,
                            channel, value_type, value_data, task_path
                        ) VALUES (:tid, :ns, :cid, :task_id, :wi, :ch, :vt, :vd, :tp)
                        ON CONFLICT(thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                        DO UPDATE SET
                            channel = excluded.channel,
                            value_type = excluded.value_type,
                            value_data = excluded.value_data,
                            task_path = excluded.task_path
                    """),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "cid": checkpoint_id,
                        "task_id": task_id,
                        "wi": write_idx,
                        "ch": channel,
                        "vt": value_type,
                        "vd": value_data,
                        "tp": task_path,
                    },
                )

    def delete_thread(self, thread_id: str) -> None:
        engine = get_engine()
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM agent_checkpoint_writes WHERE thread_id = :tid"),
                {"tid": thread_id},
            )
            connection.execute(
                text("DELETE FROM agent_checkpoint_blobs WHERE thread_id = :tid"),
                {"tid": thread_id},
            )
            connection.execute(
                text("DELETE FROM agent_checkpoints WHERE thread_id = :tid"),
                {"tid": thread_id},
            )

    def delete_namespace(self, thread_id: str, checkpoint_ns: str) -> None:
        engine = get_engine()
        with engine.begin() as connection:
            connection.execute(
                text("""
                    DELETE FROM agent_checkpoint_writes
                    WHERE thread_id = :tid AND checkpoint_ns = :ns
                """),
                {"tid": thread_id, "ns": checkpoint_ns},
            )
            connection.execute(
                text("""
                    DELETE FROM agent_checkpoint_blobs
                    WHERE thread_id = :tid AND checkpoint_ns = :ns
                """),
                {"tid": thread_id, "ns": checkpoint_ns},
            )
            connection.execute(
                text("""
                    DELETE FROM agent_checkpoints
                    WHERE thread_id = :tid AND checkpoint_ns = :ns
                """),
                {"tid": thread_id, "ns": checkpoint_ns},
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
        engine = get_engine()
        with engine.connect() as connection:
            for channel, version in versions.items():
                row = connection.execute(
                    text("""
                        SELECT value_type, value_data
                        FROM agent_checkpoint_blobs
                        WHERE thread_id = :tid AND checkpoint_ns = :ns AND channel = :ch AND version = :ver
                    """),
                    {
                        "tid": thread_id,
                        "ns": checkpoint_ns,
                        "ch": str(channel),
                        "ver": str(version),
                    },
                ).fetchone()
                if row is None or row[0] == "empty":
                    continue
                channel_values[str(channel)] = self._deserialize_typed(
                    str(row[0]),
                    bytes(row[1]),
                )
        return channel_values

    def _deserialize_typed(self, value_type: str, value_data: bytes) -> Any:
        return self.serde.loads_typed((value_type, value_data))


checkpoint_saver = DatabaseCheckpointSaver()
