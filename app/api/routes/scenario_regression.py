"""Scenario regression APIs for development-stage readiness evaluation."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.providers import get_scenario_regression_service
from app.api.responses import json_response
from app.application.scenario_regression_service import ScenarioRegressionService
from app.security import Principal, require_capability

router = APIRouter()


class ScenarioEvaluationRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)


@router.get("/scenario-regression/scenarios")
async def list_scenario_regression_scenarios(
    _principal: Principal = Depends(require_capability("aiops:run")),
    scenario_service: ScenarioRegressionService = Depends(get_scenario_regression_service),
):
    scenarios = scenario_service.list_scenarios()
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": scenarios},
    )


@router.post("/scenario-regression/evaluations")
async def evaluate_scenario_regression_run(
    request: ScenarioEvaluationRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
    scenario_service: ScenarioRegressionService = Depends(get_scenario_regression_service),
):
    try:
        evaluation = scenario_service.evaluate_run(
            scenario_id=request.scenario_id,
            run_id=request.run_id,
        )
    except ValueError as _exc:
        return JSONResponse(status_code=404, content={"code": 404, "message": "run_not_found"})
    if evaluation is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "run_not_found"})
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": evaluation},
    )
