"""API response helpers."""

from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


def json_response(*, status_code: int, content: Any) -> JSONResponse:
    """Return a JSON response after converting values such as datetime."""
    return JSONResponse(status_code=status_code, content=jsonable_encoder(content))


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """Return the shared API error envelope."""
    data: dict[str, Any] = {
        "success": False,
        "errorCode": code,
        "errorMessage": message,
    }
    if request_id:
        data["requestId"] = request_id
    if details:
        data["details"] = details
    return json_response(
        status_code=status_code,
        content={
            "code": status_code,
            "message": code,
            "data": data,
        },
    )
