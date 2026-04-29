"""Native Agent product APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.responses import json_response
from app.core.container import service_container
from app.domains.native_agent import (
    AgentFeedbackCreateRequest,
    AgentRunCreateRequest,
    SceneCreateRequest,
    ToolPolicyUpdateRequest,
    WorkspaceCreateRequest,
)
from app.security import Principal, require_capability

router = APIRouter()


@router.post("/workspaces")
async def create_workspace(
    request: WorkspaceCreateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    workspace = service_container.get_native_agent_application_service().create_workspace(
        name=request.name,
        description=request.description,
    )
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": workspace,
        },
    )


@router.get("/workspaces")
async def list_workspaces(
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    workspaces = service_container.get_native_agent_application_service().list_workspaces()
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": workspaces,
        },
    )


@router.post("/scenes")
async def create_scene(
    request: SceneCreateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    scene = service_container.get_native_agent_application_service().create_scene(
        workspace_id=request.workspace_id,
        name=request.name,
        description=request.description,
        knowledge_base_ids=request.knowledge_base_ids,
        tool_names=request.tool_names,
        agent_config=request.agent_config,
    )
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": scene,
        },
    )


@router.get("/scenes")
async def list_scenes(
    workspace_id: str | None = None,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    scenes = service_container.get_native_agent_application_service().list_scenes(
        workspace_id=workspace_id
    )
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": scenes,
        },
    )


@router.get("/scenes/{scene_id}")
async def get_scene(
    scene_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    scene = service_container.get_native_agent_application_service().get_scene(scene_id)
    if scene is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": scene},
    )


@router.get("/tools")
async def list_tools(
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    data = await service_container.get_native_agent_application_service().list_tools()
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": data},
    )


@router.patch("/tools/{tool_name}/policy")
async def update_tool_policy(
    tool_name: str,
    request: ToolPolicyUpdateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    policy = service_container.get_native_agent_application_service().update_tool_policy(
        tool_name,
        scope=request.scope,
        risk_level=request.risk_level,
        capability=request.capability,
        enabled=request.enabled,
        approval_required=request.approval_required,
    )
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": policy},
    )


@router.post("/agent/runs")
async def create_agent_run(
    request: AgentRunCreateRequest,
    principal: Principal = Depends(require_capability("aiops:run")),
):
    run = await service_container.get_native_agent_application_service().create_agent_run(
        scene_id=request.scene_id,
        session_id=request.session_id,
        goal=request.goal,
        principal=principal,
    )

    if run is None:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "agent_run_empty"},
        )
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": run,
        },
    )


@router.get("/agent/runs/{run_id}")
async def get_agent_run(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    run = service_container.get_native_agent_application_service().get_agent_run(run_id)
    if run is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": run},
    )


@router.get("/agent/runs/{run_id}/events")
async def list_agent_run_events(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    events = service_container.get_native_agent_application_service().list_agent_run_events(run_id)
    if events is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": events,
        },
    )


@router.post("/agent/runs/{run_id}/feedback")
async def create_agent_feedback(
    run_id: str,
    request: AgentFeedbackCreateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    feedback = service_container.get_native_agent_application_service().create_agent_feedback(
        run_id,
        rating=request.rating,
        comment=request.comment,
    )
    if feedback is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": feedback,
        },
    )
