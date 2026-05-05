"""Export and check the FastAPI OpenAPI contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_PATH = ROOT / "docs" / "openapi.json"
HTTP_METHODS = {
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
}


class OpenAPIContractError(RuntimeError):
    """Raised when the generated OpenAPI contract is invalid."""


def build_openapi_contract() -> dict[str, Any]:
    """Build the OpenAPI contract without starting the application lifespan."""
    from app.main import app

    spec = app.openapi()
    if not isinstance(spec, dict):
        raise OpenAPIContractError("FastAPI returned a non-object OpenAPI contract")

    _validate_operation_ids(spec)
    return spec


def _validate_operation_ids(spec: dict[str, Any]) -> None:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise OpenAPIContractError("OpenAPI contract is missing a paths object")

    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if str(method).lower() not in HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id:
                raise OpenAPIContractError(f"{method.upper()} {path} is missing operationId")

            location = f"{method.upper()} {path}"
            if operation_id in seen:
                duplicates.append(f"{operation_id}: {seen[operation_id]} and {location}")
            else:
                seen[operation_id] = location

    if duplicates:
        duplicate_text = "\n".join(f"- {item}" for item in duplicates)
        raise OpenAPIContractError(f"Duplicate OpenAPI operationId values:\n{duplicate_text}")


def render_contract(spec: dict[str, Any]) -> str:
    """Render the OpenAPI contract in a stable, reviewable format."""
    return json.dumps(spec, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_contract() -> None:
    OPENAPI_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPENAPI_PATH.write_text(render_contract(build_openapi_contract()), encoding="utf-8")


def check_contract() -> None:
    expected = render_contract(build_openapi_contract())
    if not OPENAPI_PATH.exists():
        raise OpenAPIContractError(
            f"{OPENAPI_PATH.relative_to(ROOT)} does not exist. "
            "Run `python scripts/export_openapi.py --write`."
        )

    current = OPENAPI_PATH.read_text(encoding="utf-8")
    if current != expected:
        raise OpenAPIContractError(
            f"{OPENAPI_PATH.relative_to(ROOT)} is out of date. "
            "Run `python scripts/export_openapi.py --write` and commit the result."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true", help="write docs/openapi.json")
    group.add_argument("--check", action="store_true", help="check docs/openapi.json is current")
    args = parser.parse_args()

    try:
        if args.write:
            write_contract()
            print(f"Wrote {OPENAPI_PATH.relative_to(ROOT)}")
        else:
            check_contract()
            print(f"OpenAPI contract is current: {OPENAPI_PATH.relative_to(ROOT)}")
    except OpenAPIContractError as exc:
        print(f"OpenAPI contract check failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
