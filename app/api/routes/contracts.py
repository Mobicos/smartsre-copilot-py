"""API contract governance endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.providers import get_api_contract_service
from app.api.responses import json_response
from app.application.api_contract_service import ApiContractService
from app.security import Principal, require_capability

router = APIRouter()


@router.get("/contracts/openapi")
async def get_openapi_contract(
    include_spec: bool = Query(default=False),
    _principal: Principal = Depends(require_capability("aiops:run")),
    contract_service: ApiContractService = Depends(get_api_contract_service),
):
    contract = contract_service.summarize()
    if not include_spec:
        contract = {
            **contract,
            "current_spec": None,
            "snapshot_spec": None,
        }
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": contract,
        },
    )
