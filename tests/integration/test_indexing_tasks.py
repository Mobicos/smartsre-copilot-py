from __future__ import annotations

import json
from datetime import UTC, datetime

from app.api import providers
from app.api.routes.file import get_index_task
from app.config import config
from app.platform.persistence import indexing_task_repository
from app.security import Principal


def test_submit_task_reuses_active_task():
    indexing_task_service = providers.get_indexing_task_service()
    task_id = indexing_task_repository.create_task(
        "ops.md",
        "/tmp/ops.md",
        max_retries=3,
    )

    reused_task_id = indexing_task_service.submit_task("ops.md", "/tmp/ops.md")

    assert reused_task_id == task_id
    tasks = indexing_task_repository.list_tasks_by_status(["queued"])
    assert len(tasks) == 1


def test_indexing_task_retries_then_fails_permanently(monkeypatch):
    indexing_task_service = providers.get_indexing_task_service()
    config.indexing_task_max_retries = 2
    task_id = indexing_task_service.submit_task("ops.md", "/tmp/ops.md")

    def raise_index_error(file_path: str) -> None:
        raise RuntimeError(f"boom:{file_path}")

    class FailingVectorIndexService:
        @staticmethod
        def index_single_file(file_path: str) -> None:
            raise_index_error(file_path)

    monkeypatch.setattr(
        providers,
        "get_vector_index_service",
        lambda: FailingVectorIndexService(),
    )

    claimed = indexing_task_repository.claim_task(task_id)
    assert claimed is not None
    assert claimed["attempt_count"] == 1

    first_result = indexing_task_service.process_task(task_id, "/tmp/ops.md")
    first_task = indexing_task_repository.get_task(task_id)

    assert first_result == "queued"
    assert first_task is not None
    assert first_task["status"] == "queued"
    assert first_task["attempt_count"] == 1
    assert first_task["max_retries"] == 2
    assert "boom:/tmp/ops.md" in str(first_task["error_message"])

    claimed_again = indexing_task_repository.claim_task(task_id)
    assert claimed_again is not None
    assert claimed_again["attempt_count"] == 2

    second_result = indexing_task_service.process_task(task_id, "/tmp/ops.md")
    second_task = indexing_task_repository.get_task(task_id)

    assert second_result == "failed_permanently"
    assert second_task is not None
    assert second_task["status"] == "failed_permanently"
    assert second_task["attempt_count"] == 2


def test_requeue_stale_processing_task_respects_retry_limit():
    task_id = indexing_task_repository.create_task(
        "ops.md",
        "/tmp/ops.md",
        max_retries=1,
    )
    claimed = indexing_task_repository.claim_task(task_id)
    assert claimed is not None

    requeued_count = indexing_task_repository.requeue_stale_processing_tasks(0)
    task = indexing_task_repository.get_task(task_id)

    assert requeued_count == 1
    assert task is not None
    assert task["status"] == "failed_permanently"
    assert "retry limit" in str(task["error_message"])


async def test_get_index_task_serializes_datetime_values(monkeypatch):
    created_at = datetime(2026, 4, 24, 10, 4, 39, 162899, tzinfo=UTC)
    updated_at = datetime(2026, 4, 24, 10, 5, 1, tzinfo=UTC)

    monkeypatch.setattr(
        indexing_task_repository,
        "get_task",
        lambda task_id: {
            "task_id": task_id,
            "filename": "ops.md",
            "file_path": "/tmp/ops.md",
            "status": "completed",
            "attempt_count": 1,
            "max_retries": 3,
            "error_message": None,
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )

    response = await get_index_task(
        "task-1",
        _principal=Principal(role="admin", subject="test"),
    )
    payload = json.loads(response.body)

    assert payload["data"]["created_at"] == created_at.isoformat()
    assert payload["data"]["updated_at"] == updated_at.isoformat()
