"""OpenAPI contract snapshot and diff service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.config import BASE_DIR

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
OPENAPI_SNAPSHOT_PATH = BASE_DIR / "docs" / "openapi.json"


@dataclass(frozen=True)
class ApiOperation:
    path: str
    method: str
    operation_id: str | None
    summary: str | None
    tags: list[str]
    fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "method": self.method,
            "operation_id": self.operation_id,
            "summary": self.summary,
            "tags": self.tags,
            "fingerprint": self.fingerprint,
        }


class ApiContractService:
    """Build the current OpenAPI contract and compare it to the snapshot."""

    def __init__(self, *, snapshot_path: Path = OPENAPI_SNAPSHOT_PATH) -> None:
        self._snapshot_path = snapshot_path

    def summarize(self) -> dict[str, Any]:
        current = self._build_current_spec()
        snapshot = self._load_snapshot()
        current_operations = self._collect_operations(current)
        snapshot_operations = self._collect_operations(snapshot) if snapshot else []
        diff = self._diff_operations(current_operations, snapshot_operations)

        return {
            "snapshot_path": str(self._snapshot_path.relative_to(BASE_DIR)),
            "snapshot_exists": snapshot is not None,
            "current": _spec_summary(current, current_operations),
            "snapshot": _spec_summary(snapshot, snapshot_operations) if snapshot else None,
            "diff": diff,
            "current_spec": current,
            "snapshot_spec": snapshot,
        }

    def _build_current_spec(self) -> dict[str, Any]:
        from app.main import app

        spec = app.openapi()
        if not isinstance(spec, dict):
            raise RuntimeError("OpenAPI contract must be a JSON object")
        return spec

    def _load_snapshot(self) -> dict[str, Any] | None:
        if not self._snapshot_path.exists():
            return None
        payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None

    def _collect_operations(self, spec: dict[str, Any] | None) -> list[ApiOperation]:
        if not spec:
            return []
        operations: list[ApiOperation] = []
        paths = spec.get("paths")
        if not isinstance(paths, dict):
            return []
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if str(method).lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                operations.append(
                    ApiOperation(
                        path=str(path),
                        method=str(method).upper(),
                        operation_id=operation.get("operationId")
                        if isinstance(operation.get("operationId"), str)
                        else None,
                        summary=operation.get("summary")
                        if isinstance(operation.get("summary"), str)
                        else None,
                        tags=[str(tag) for tag in operation.get("tags", []) if str(tag)],
                        fingerprint=_fingerprint(operation),
                    )
                )
        return operations

    def _diff_operations(
        self,
        current: list[ApiOperation],
        snapshot: list[ApiOperation],
    ) -> dict[str, Any]:
        snapshot_map = {_operation_key(operation): operation for operation in snapshot}
        current_map = {_operation_key(operation): operation for operation in current}

        added = [
            operation.to_dict() for key, operation in current_map.items() if key not in snapshot_map
        ]
        removed = [
            operation.to_dict() for key, operation in snapshot_map.items() if key not in current_map
        ]
        changed = []
        for key, operation in current_map.items():
            previous = snapshot_map.get(key)
            if previous is None or previous.fingerprint == operation.fingerprint:
                continue
            changed.append(
                {
                    "path": operation.path,
                    "method": operation.method,
                    "operation_id": operation.operation_id,
                    "current": operation.to_dict(),
                    "previous": previous.to_dict(),
                }
            )

        return {
            "status": "synced" if not added and not removed and not changed else "out_of_date",
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
            "added_operations": added,
            "removed_operations": removed,
            "changed_operations": changed,
        }


def _operation_key(operation: ApiOperation) -> str:
    return f"{operation.method} {operation.path}"


def _fingerprint(operation: dict[str, Any]) -> str:
    normalized = json.dumps(operation, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return sha256(normalized.encode("utf-8")).hexdigest()


def _spec_summary(spec: dict[str, Any] | None, operations: list[ApiOperation]) -> dict[str, Any]:
    if not spec:
        return {
            "title": None,
            "version": None,
            "path_count": 0,
            "operation_count": 0,
            "tags": [],
        }

    raw_info = spec.get("info")
    info: dict[str, Any] = raw_info if isinstance(raw_info, dict) else {}
    raw_tags = spec.get("tags")
    tags: list[Any] = raw_tags if isinstance(raw_tags, list) else []
    raw_paths = spec.get("paths")
    return {
        "title": info.get("title"),
        "version": info.get("version"),
        "path_count": len(raw_paths) if isinstance(raw_paths, dict) else 0,
        "operation_count": len(operations),
        "tags": [str(tag.get("name")) for tag in tags if isinstance(tag, dict) and tag.get("name")],
    }
