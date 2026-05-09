"""对话接口。"""

from fastapi import APIRouter, Depends
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.api.providers import get_chat_application_service, get_rag_agent_service
from app.api.responses import json_response
from app.application.chat import RagAgentService
from app.application.chat_application_service import ChatApplicationService
from app.core.exceptions import InfrastructureException
from app.domains.chat import ApiResponse, ChatRequest, ClearRequest, SessionInfoResponse
from app.platform.persistence import chat_tool_event_repository, conversation_repository
from app.security import Principal, require_capability, require_stream_rate_limit

router = APIRouter()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    _principal: Principal = Depends(require_capability("chat:use")),
    chat_application_service: ChatApplicationService = Depends(get_chat_application_service),
):
    """快速对话接口
    {
        "code": 200,
        "message": "success",
        "data": {
            "success": true,
            "answer": "回答内容",
            "errorMessage": null
        }
    }

    Args:
        request: 对话请求

    Returns:
        统一格式的对话响应
    """
    try:
        logger.info(f"[会话 {request.id}] 收到快速对话请求: {request.question}")
        result = await chat_application_service.run_chat(request.id, request.question)

        logger.info(f"[会话 {request.id}] 快速对话完成")

        return json_response(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "success": True,
                    "answer": result["answer"],
                    "toolEvents": result["toolEvents"],
                    "exchangeId": result["exchangeId"],
                    "errorMessage": None,
                },
            },
        )

    except Exception as e:
        logger.error(f"对话接口错误: {e}")
        raise InfrastructureException("chat_request_failed", code="chat_request_failed") from e


@router.post("/chat_stream", include_in_schema=False)
@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequest,
    _principal: Principal = Depends(require_stream_rate_limit("chat:use")),
    chat_application_service: ChatApplicationService = Depends(get_chat_application_service),
):
    """流式对话接口（基于 RAG Agent，SSE）

    返回 SSE 格式，data 字段为 JSON：

    工具调用事件:
    event: message
    data: {"type":"tool_call","data":{"tool":"工具名","status":"start|end","input":{...}}}

    内容流式事件:
    event: message
    data: {"type":"content","data":"内容块"}

    完成事件:
    event: message
    data: {"type":"done","data":{"answer":"完整答案","tool_calls":[...]}}

    Args:
        request: 对话请求

    Returns:
        SSE 事件流
    """
    logger.info(f"[会话 {request.id}] 收到流式对话请求: {request.question}")

    return EventSourceResponse(chat_application_service.stream_chat(request.id, request.question))


@router.post("/chat/clear", response_model=ApiResponse)
async def clear_session(
    request: ClearRequest,
    _principal: Principal = Depends(require_capability("chat:use")),
    chat_application_service: ChatApplicationService = Depends(get_chat_application_service),
):
    """清空会话历史

    Args:
        request: 清空请求

    Returns:
        操作结果
    """
    try:
        success = chat_application_service.clear_session(request.session_id)
        logger.info(f"清空会话: {request.session_id}, 结果: {success}")

        return ApiResponse(
            status="success" if success else "error",
            message="会话已清空" if success else "清空会话失败",
            data=None,
        )

    except Exception as e:
        logger.error(f"清空会话错误: {e}")
        raise InfrastructureException("chat_clear_failed", code="chat_clear_failed") from e


@router.get("/chat/sessions")
async def list_sessions(
    _principal: Principal = Depends(require_capability("chat:read")),
):
    """列出已持久化的会话摘要。"""
    try:
        sessions = conversation_repository.list_sessions()
        return json_response(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": sessions,
            },
        )
    except Exception as e:
        logger.error(f"获取会话列表错误: {e}")
        raise InfrastructureException("chat_sessions_failed", code="chat_sessions_failed") from e


@router.get("/chat/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(
    session_id: str,
    _principal: Principal = Depends(require_capability("chat:read")),
    rag_agent_service: RagAgentService = Depends(get_rag_agent_service),
) -> SessionInfoResponse:
    """查询会话历史

    Args:
        session_id: 会话 ID

    Returns:
        会话信息
    """
    try:
        history = [
            message.to_dict()
            for message in conversation_repository.get_session_messages(session_id)
        ]
        if not history:
            history = rag_agent_service.get_session_history(session_id)

        return SessionInfoResponse(
            session_id=session_id, message_count=len(history), history=history
        )

    except Exception as e:
        logger.error(f"获取会话信息错误: {e}")
        raise InfrastructureException("chat_session_failed", code="chat_session_failed") from e


@router.get("/chat/session/{session_id}/tool-events")
async def get_session_tool_events(
    session_id: str,
    _principal: Principal = Depends(require_capability("chat:read")),
):
    """查询会话工具调用事件。"""
    try:
        return json_response(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": chat_tool_event_repository.list_events(session_id),
            },
        )
    except Exception as e:
        logger.error(f"获取工具事件错误: {e}")
        raise InfrastructureException(
            "chat_tool_events_failed", code="chat_tool_events_failed"
        ) from e
