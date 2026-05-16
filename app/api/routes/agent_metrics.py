"""Aggregate AgentOps metrics API for Release Gate."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.providers import get_agent_metrics_service
from app.api.responses import json_response
from app.application.agent_metrics_service import AgentMetricsService
from app.security import Principal, require_capability

router = APIRouter()


@router.get("/agent/metrics/release-gate")
async def get_release_gate_metrics(
    limit: int = 100,
    _principal: Principal = Depends(require_capability("aiops:run")),
    metrics_service: AgentMetricsService = Depends(get_agent_metrics_service),
):
    result = metrics_service.compute_release_gate(limit=limit)
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": result},
    )


@router.get("/agent/metrics/summary")
async def get_metrics_summary(
    limit: int = 50,
    _principal: Principal = Depends(require_capability("aiops:run")),
    metrics_service: AgentMetricsService = Depends(get_agent_metrics_service),
):
    result = metrics_service.compute_summary(limit=limit)
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": result},
    )
