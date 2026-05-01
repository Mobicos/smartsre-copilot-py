"""
AIOps 智能运维接口
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.api.responses import json_response
from app.core.container import service_container
from app.domains.aiops import AIOpsRequest
from app.platform.persistence import aiops_run_repository
from app.security import Principal, require_capability

router = APIRouter()


@router.post("/aiops")
async def diagnose_stream(
    request: AIOpsRequest,
    principal: Principal = Depends(require_capability("aiops:run")),
):
    """
    AIOps 故障诊断接口（流式 SSE）

    **功能说明：**
    - 自动获取当前系统的活动告警
    - 使用 Plan-Execute-Replan 模式进行智能诊断
    - 流式返回诊断过程和结果

    **SSE 事件类型：**

    1. `status` - 状态更新
       ```json
       {
         "type": "status",
         "stage": "fetching_alerts",
         "message": "正在获取系统告警信息..."
       }
       ```

    2. `plan` - 诊断计划制定完成
       ```json
       {
         "type": "plan",
         "stage": "plan_created",
         "message": "诊断计划已制定，共 6 个步骤",
         "target_alert": {...},
         "plan": ["步骤1: ...", "步骤2: ..."]
       }
       ```

    3. `step_complete` - 步骤执行完成
       ```json
       {
         "type": "step_complete",
         "stage": "step_executed",
         "message": "步骤执行完成 (2/6)",
         "current_step": "查询系统日志",
         "result_preview": "...",
         "remaining_steps": 4
       }
       ```

    4. `report` - 最终诊断报告
       ```json
       {
         "type": "report",
         "stage": "final_report",
         "message": "最终诊断报告已生成",
         "report": "# 故障诊断报告\\n...",
         "evidence": {...}
       }
       ```

    5. `complete` - 诊断完成
       ```json
       {
         "type": "complete",
         "stage": "diagnosis_complete",
         "message": "诊断流程完成",
         "diagnosis": {...}
       }
       ```

    6. `error` - 错误信息
       ```json
       {
         "type": "error",
         "stage": "error",
         "message": "诊断过程发生错误: ..."
       }
       ```

    **使用示例：**
    ```bash
    curl -X POST "http://localhost:9900/api/aiops" \\
      -H "Content-Type: application/json" \\
      -d '{"session_id": "session-123"}' \\
      --no-buffer
    ```

    **前端使用示例：**
    ```javascript
    const eventSource = new EventSource('/api/aiops');

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.type === 'plan') {
        console.log('诊断计划:', data.plan);
      } else if (data.type === 'step_complete') {
        console.log('步骤完成:', data.current_step);
      } else if (data.type === 'report') {
        console.log('最终报告:', data.report);
      } else if (data.type === 'complete') {
        console.log('诊断完成');
        eventSource.close();
      }
    };
    ```

    Args:
        request: AIOps 诊断请求

    Returns:
        SSE 事件流
    """
    session_id = request.session_id or "default"
    task_input = request.diagnosis_goal()
    aiops_application_service = service_container.get_aiops_application_service()
    logger.info(f"[会话 {session_id}] 收到 AIOps 诊断请求（流式）")
    return EventSourceResponse(
        aiops_application_service.stream_diagnosis(
            session_id,
            task_input=task_input,
            principal=principal,
        )
    )


@router.get("/aiops/runs/{run_id}")
async def get_aiops_run(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    """查询 AIOps 运行摘要。"""
    run = aiops_run_repository.get_run(run_id)
    if run is None:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "not_found", "data": None},
        )

    return json_response(
        status_code=200,
        content={"code": 200, "message": "success", "data": run},
    )


@router.get("/aiops/runs/{run_id}/events")
async def list_aiops_run_events(
    run_id: str,
    _principal: Principal = Depends(require_capability("aiops:run")),
):
    """查询 AIOps 运行过程事件。"""
    run = aiops_run_repository.get_run(run_id)
    if run is None:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "message": "not_found", "data": None},
        )

    return json_response(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": aiops_run_repository.list_events(run_id),
        },
    )
