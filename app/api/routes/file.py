"""Knowledge document upload and indexing APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.providers import (
    get_indexing_task_service,
    get_object_storage,
    get_vector_index_service,
    get_vector_store_manager,
)
from app.api.responses import json_response
from app.config import UPLOADS_DIR
from app.core.exceptions import InfrastructureException
from app.infrastructure.tasks import task_dispatcher
from app.platform.persistence.repositories.indexing import indexing_task_repository
from app.security import Principal, require_capability

router = APIRouter()

UPLOAD_DIR = UPLOADS_DIR
ALLOWED_EXTENSIONS = ["txt", "md"]
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    _principal: Principal = Depends(require_capability("knowledge:write")),
):
    """Upload a knowledge document and enqueue indexing."""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="filename_required")

        safe_filename = _sanitize_filename(file.filename)
        file_extension = _get_file_extension(safe_filename)
        if file_extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"unsupported_file_type:{','.join(ALLOWED_EXTENSIONS)}",
            )

        content = await file.read()
        _validate_upload_content(content)

        stored_object = get_object_storage().put_bytes(safe_filename, content)
        file_path = stored_object.local_path
        logger.info(f"Uploaded knowledge object {stored_object.uri} to {file_path}")

        task_id = get_indexing_task_service().submit_task(
            safe_filename,
            safe_filename,
        )
        await task_dispatcher.enqueue_indexing_task(
            task_id,
            safe_filename,
        )

        return json_response(
            status_code=202,
            content={
                "code": 202,
                "message": "accepted",
                "data": {
                    "filename": safe_filename,
                    "file_path": str(file_path),
                    "object_uri": stored_object.uri,
                    "storage_backend": stored_object.backend,
                    "size": stored_object.size,
                    "indexing": {
                        "taskId": task_id,
                        "status": "queued",
                    },
                },
            },
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"File upload failed: {exc}")
        raise InfrastructureException("file_upload_failed", code="file_upload_failed") from exc


@router.post("/index_directory")
async def index_directory(
    directory_path: str | None = None,
    _principal: Principal = Depends(require_capability("knowledge:write")),
):
    """Index a local directory of supported knowledge documents."""
    try:
        logger.info(f"Indexing directory: {directory_path or 'uploads'}")
        result = get_vector_index_service().index_directory(directory_path)
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success" if result.success else "partial_success",
                "data": result.to_dict(),
            },
        )
    except Exception as exc:
        logger.error(f"Index directory failed: {exc}")
        raise InfrastructureException(
            "index_directory_failed", code="index_directory_failed"
        ) from exc


@router.get("/index_tasks")
async def list_index_tasks(
    status: list[str] | None = Query(default=None),
    _principal: Principal = Depends(require_capability("knowledge:read")),
):
    """List indexing tasks by status."""
    statuses = status or sorted(indexing_task_repository.ALLOWED_TASK_STATUSES)
    try:
        tasks = indexing_task_repository.list_tasks_by_status(statuses)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": {
                "statuses": statuses,
                "tasks": tasks,
            },
        },
    )


@router.get("/index_tasks/{task_id}")
async def get_index_task(
    task_id: str,
    _principal: Principal = Depends(require_capability("knowledge:read")),
):
    """Return one indexing task."""
    task = indexing_task_repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="indexing_task_not_found")

    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": task,
        },
    )


@router.post("/index_tasks/{task_id}/retry")
async def retry_index_task(
    task_id: str,
    _principal: Principal = Depends(require_capability("knowledge:write")),
):
    """Requeue a failed or queued indexing task."""
    task = indexing_task_repository.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="indexing_task_not_found")

    if task.get("status") == "processing":
        raise HTTPException(status_code=409, detail="indexing_task_processing")

    indexing_task_repository.update_task(task_id, status="queued", error_message=None)
    await task_dispatcher.enqueue_indexing_task(task_id, str(task["file_path"]))
    requeued = indexing_task_repository.get_task(task_id)
    return json_response(
        status_code=202,
        content={
            "code": 202,
            "message": "accepted",
            "data": requeued,
        },
    )


@router.delete("/documents/{filename}")
async def delete_uploaded_document(
    filename: str,
    _principal: Principal = Depends(require_capability("knowledge:write")),
):
    """Delete an uploaded document and remove its vector-store entries."""
    safe_filename = _sanitize_filename(filename)
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="invalid_filename")

    object_storage = get_object_storage()
    file_path = object_storage.local_path_for(safe_filename)
    try:
        deleted_object = object_storage.delete(safe_filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    deleted_vectors = get_vector_store_manager().delete_by_source(file_path.as_posix())
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": {
                "filename": safe_filename,
                "file_path": str(file_path),
                "object_uri": deleted_object.uri,
                "storage_backend": deleted_object.backend,
                "deleted_file": deleted_object.deleted_local,
                "deleted_remote": deleted_object.deleted_remote,
                "deleted_vectors": deleted_vectors,
            },
        },
    )


def _get_file_extension(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    if len(parts) == 2:
        return parts[1].lower()
    return ""


def _sanitize_filename(filename: str) -> str:
    sanitized = filename.replace(" ", "_")
    for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
        sanitized = sanitized.replace(char, "_")
    return sanitized


def _validate_upload_content(content: bytes) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="empty_file")

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"file_too_large:{MAX_FILE_SIZE}")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="file_must_be_utf8") from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="empty_text")
