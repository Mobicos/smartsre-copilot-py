from __future__ import annotations

from app.config import config
from app.infrastructure.tasks import LocalTaskDispatcher


async def test_database_enqueue_wakes_embedded_worker(monkeypatch):
    dispatcher = LocalTaskDispatcher()
    monkeypatch.setattr(config, "task_queue_backend", "database")
    dispatcher._started = True

    await dispatcher.enqueue_indexing_task("task-1", "/tmp/ops.md")

    assert dispatcher._wake_event.is_set()


async def test_redis_enqueue_publishes_task_payload(monkeypatch):
    dispatcher = LocalTaskDispatcher()
    published: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(config, "task_queue_backend", "redis")
    monkeypatch.setattr(config, "redis_task_queue_name", "queue")
    monkeypatch.setattr(
        "app.infrastructure.tasks.dispatcher.redis_manager.enqueue_json",
        lambda queue, payload: published.append((queue, payload)),
    )

    await dispatcher.enqueue_indexing_task("task-1", "/tmp/ops.md")

    assert published == [("queue", {"task_id": "task-1", "file_path": "/tmp/ops.md"})]


def test_republish_queued_tasks_to_redis(monkeypatch):
    dispatcher = LocalTaskDispatcher()
    published: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(config, "redis_task_queue_name", "queue")
    monkeypatch.setattr(
        "app.infrastructure.tasks.dispatcher.indexing_task_repository.list_tasks_by_status",
        lambda statuses: [
            {"task_id": "task-1", "file_path": "/tmp/a.md"},
            {"task_id": "task-2", "file_path": "/tmp/b.md"},
        ],
    )
    monkeypatch.setattr(
        "app.infrastructure.tasks.dispatcher.redis_manager.enqueue_json",
        lambda queue, payload: published.append((queue, payload)),
    )

    dispatcher._republish_queued_tasks_to_redis()

    assert published == [
        ("queue", {"task_id": "task-1", "file_path": "/tmp/a.md"}),
        ("queue", {"task_id": "task-2", "file_path": "/tmp/b.md"}),
    ]
