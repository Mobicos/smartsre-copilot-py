"""Native Agent product APIs."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.api.providers import get_agent_resume_service, get_native_agent_application_service
from app.api.responses import json_response
from app.application.agent_resume_service import AgentResumeService
from app.application.native_agent_application_service import NativeAgentApplicationService
from app.core.exceptions import InfrastructureException
from app.domains.native_agent import (
    AgentFeedbackCreateRequest,
    AgentRunCreateRequest,
    SceneCreateRequest,
    ToolPolicyUpdateRequest,
    WorkspaceCreateRequest,
)
from app.security import Principal, require_capability

router = APIRouter()


class AgentApprovalDecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


@router.post("/workspaces")
async def create_workspace(
    request: WorkspaceCreateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    workspace = native_agent_service.create_workspace(
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
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    workspaces = native_agent_service.list_workspaces()
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
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    scene = native_agent_service.create_scene(
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
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    scenes = native_agent_service.list_scenes(workspace_id=workspace_id)
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
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    scene = native_agent_service.get_scene(scene_id)
    if scene is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": scene},
    )


@router.get("/tools")
async def list_tools(
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    data = await native_agent_service.list_tools()
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": data},
    )


@router.patch("/tools/{tool_name}/policy")
async def update_tool_policy(
    tool_name: str,
    request: ToolPolicyUpdateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    policy = native_agent_service.update_tool_policy(
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
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    run = await native_agent_service.create_agent_run(
        scene_id=request.scene_id,
        session_id=request.session_id,
        goal=request.goal,
        principal=principal,
    )

    if run is None:
        raise InfrastructureException("agent_run_empty", code="agent_run_empty")
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": run,
        },
    )


@router.post("/agent/runs/stream")
async def stream_agent_run(
    request: AgentRunCreateRequest,
    principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    """Stream agent run events via SSE."""

    async def event_generator():
        async for event in native_agent_service.stream_agent_run(
            scene_id=request.scene_id,
            session_id=request.session_id,
            goal=request.goal,
            principal=principal,
        ):
            yield {
                "event": event.get("type", "status"),
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.get("/agent/runs")
async def list_agent_runs(
    limit: int = 50,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    runs = native_agent_service.list_agent_runs(limit=limit)
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": runs},
    )


@router.get("/agent/approvals")
async def list_agent_approvals(
    limit: int = 50,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    approvals = native_agent_service.list_agent_approvals(limit=limit)
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": approvals},
    )


@router.get("/agent/runs/{run_id}")
async def get_agent_run(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    run = native_agent_service.get_agent_run(run_id)
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
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    events = native_agent_service.list_agent_run_events(run_id)
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


@router.get("/agent/runs/{run_id}/replay")
async def get_agent_run_replay(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    replay = native_agent_service.get_agent_run_replay(run_id)
    if replay is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": replay,
        },
    )


@router.get("/agent/runs/{run_id}/decision-state")
async def get_agent_decision_state(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    state = native_agent_service.get_agent_decision_state(run_id)
    if state is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": state},
    )


@router.post("/agent/runs/{run_id}/approvals/{tool_name}")
async def decide_agent_approval(
    run_id: str,
    tool_name: str,
    request: AgentApprovalDecisionRequest,
    principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    try:
        decision = native_agent_service.decide_agent_approval(
            run_id,
            tool_name=tool_name,
            decision=request.decision,
            comment=request.comment,
            actor=principal.subject,
        )
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"code": 400, "message": str(exc)})
    if decision is None:
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": decision},
    )


@router.post("/agent/runs/{run_id}/approvals/{tool_name}/resume")
async def resume_agent_approval(
    run_id: str,
    tool_name: str,
    principal: Principal = Depends(require_capability("aiops:run")),
    agent_resume_service: AgentResumeService = Depends(get_agent_resume_service),
):
    result = await agent_resume_service.process_resume_task(
        {
            "run_id": run_id,
            "tool_name": tool_name,
            "decision": "approved",
            "actor": principal.subject,
            "checkpoint_ns": "agent-v2",
        }
    )
    if result.get("reason") == "run_not_found":
        return JSONResponse(status_code=404, content={"code": 404, "message": "not_found"})
    if result.get("reason") == "approval_not_found":
        return JSONResponse(
            status_code=400,
            content={"code": 400, "message": "approval_not_found", "data": result},
        )
    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": result},
    )


@router.post("/agent/runs/{run_id}/feedback")
async def create_agent_feedback(
    run_id: str,
    request: AgentFeedbackCreateRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
    native_agent_service: NativeAgentApplicationService = Depends(
        get_native_agent_application_service
    ),
):
    feedback = native_agent_service.create_agent_feedback(
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
