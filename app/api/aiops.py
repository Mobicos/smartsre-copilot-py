"""
AIOps 智能运维接口
"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.core.container import service_container
from app.models.aiops import AIOpsRequest
from app.persistence import aiops_run_repository, conversation_repository
from app.security import Principal, require_capability

router = APIRouter()


@router.post("/aiops")
async def diagnose_stream(
    request: AIOpsRequest,
    _principal: Principal = Depends(require_capability("aiops:run")),
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
    aiops_service = service_container.get_aiops_service()
    logger.info(f"[会话 {session_id}] 收到 AIOps 诊断请求（流式）")
    run_id = aiops_run_repository.create_run(
        session_id,
        "诊断当前系统是否存在告警，如果存在告警请详细分析告警原因并生成诊断报告",
    )

    async def event_generator():
        try:
            async for event in aiops_service.diagnose(session_id=session_id):
                event_payload = {
                    **event,
                    "run_id": run_id,
                }
                aiops_run_repository.append_event(
                    run_id,
                    event_type=str(event_payload.get("type", "status")),
                    stage=str(event_payload.get("stage", "unknown")),
                    message=str(event_payload.get("message", "")),
                    payload=event_payload,
                )

                if event.get("type") == "complete":
                    report = (
                        event.get("diagnosis", {}).get("report", "")
                        if isinstance(event.get("diagnosis"), dict)
                        else ""
                    )
                    aiops_run_repository.update_run(
                        run_id,
                        status="completed",
                        report=report,
                    )
                    if report:
                        conversation_repository.save_aiops_report(
                            session_id,
                            "AIOps 自动诊断",
                            report,
                        )
                elif event.get("type") == "error":
                    aiops_run_repository.update_run(
                        run_id,
                        status="failed",
                        error_message=event.get("message", "未知错误"),
                    )

                # 发送事件
                yield {"event": "message", "data": json.dumps(event_payload, ensure_ascii=False)}

                # 如果是完成或错误事件，结束流
                if event.get("type") in ["complete", "error"]:
                    break

            logger.info(f"[会话 {session_id}] AIOps 诊断流式响应完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] AIOps 诊断流式响应异常: {e}", exc_info=True)
            aiops_run_repository.update_run(
                run_id,
                status="failed",
                error_message=str(e),
            )
            error_event = {
                "type": "error",
                "stage": "exception",
                "message": f"诊断异常: {str(e)}",
                "run_id": run_id,
            }
            aiops_run_repository.append_event(
                run_id,
                event_type="error",
                stage="exception",
                message=error_event["message"],
                payload=error_event,
            )
            yield {
                "event": "message",
                "data": json.dumps(error_event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


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

    return JSONResponse(
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

    return JSONResponse(
        status_code=200,
        content={
            "code": 200,
            "message": "success",
            "data": aiops_run_repository.list_events(run_id),
        },
    )
