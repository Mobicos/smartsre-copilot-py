"""AIOps application orchestration."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from app.persistence.repositories import AIOpsRunRepository, ConversationRepository
from app.services.aiops_service import AIOpsService


class AIOpsApplicationService:
    """Coordinate AIOps runtime and persistence."""

    def __init__(
        self,
        *,
        aiops_service: AIOpsService,
        aiops_run_repository: AIOpsRunRepository,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._aiops_service = aiops_service
        self._aiops_run_repository = aiops_run_repository
        self._conversation_repository = conversation_repository

    async def stream_diagnosis(self, session_id: str) -> AsyncGenerator[dict[str, str], None]:
        """Run a streaming diagnosis flow and persist runtime events."""
        run_id = self._aiops_run_repository.create_run(
            session_id,
            "诊断当前系统是否存在告警，如果存在告警请详细分析告警原因并生成诊断报告",
        )

        try:
            async for event in self._aiops_service.diagnose(session_id=session_id):
                event_payload = {**event, "run_id": run_id}
                self._aiops_run_repository.append_event(
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
                    self._aiops_run_repository.update_run(
                        run_id,
                        status="completed",
                        report=report,
                    )
                    if report:
                        self._conversation_repository.save_aiops_report(
                            session_id,
                            "AIOps 自动诊断",
                            report,
                        )
                elif event.get("type") == "error":
                    self._aiops_run_repository.update_run(
                        run_id,
                        status="failed",
                        error_message=event.get("message", "未知错误"),
                    )

                yield {
                    "event": "message",
                    "data": json.dumps(event_payload, ensure_ascii=False),
                }

                if event.get("type") in {"complete", "error"}:
                    break
        except Exception as exc:
            self._aiops_run_repository.update_run(
                run_id,
                status="failed",
                error_message=str(exc),
            )
            error_event = {
                "type": "error",
                "stage": "exception",
                "message": f"诊断异常: {str(exc)}",
                "run_id": run_id,
            }
            self._aiops_run_repository.append_event(
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
