"""对话接口

提供基于 RAG Agent 的普通对话和流式对话接口
"""

import json
import uuid
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from app.core.container import service_container
from app.models.request import ChatRequest, ClearRequest
from app.models.response import ApiResponse, SessionInfoResponse
from app.persistence import chat_tool_event_repository, conversation_repository
from app.security import Principal, require_capability

router = APIRouter()


@router.post("/chat")
async def chat(
    request: ChatRequest,
    _principal: Principal = Depends(require_capability("chat:use")),
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
        rag_agent_service = service_container.get_rag_agent_service()
        exchange_id = str(uuid.uuid4())
        logger.info(f"[会话 {request.id}] 收到快速对话请求: {request.question}")
        result = await rag_agent_service.query(request.question, session_id=request.id)
        conversation_repository.save_chat_exchange(request.id, request.question, result.answer)
        chat_tool_event_repository.append_events(
            request.id,
            exchange_id=exchange_id,
            events=result.tool_events,
        )

        logger.info(f"[会话 {request.id}] 快速对话完成")

        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": {
                    "success": True,
                    "answer": result.answer,
                    "toolEvents": result.tool_events,
                    "errorMessage": None,
                },
            },
        )

    except Exception as e:
        logger.error(f"对话接口错误: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "error",
                "data": {
                    "success": False,
                    "answer": None,
                    "errorMessage": str(e),
                },
            },
        )


@router.post("/chat_stream")
async def chat_stream(
    request: ChatRequest,
    _principal: Principal = Depends(require_capability("chat:use")),
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
    rag_agent_service = service_container.get_rag_agent_service()
    exchange_id = str(uuid.uuid4())

    async def event_generator():
        full_response = ""
        tool_events: list[dict[str, Any]] = []
        try:
            async for chunk in rag_agent_service.query_stream(
                request.question, session_id=request.id
            ):
                chunk_type = chunk.get("type", "unknown")
                chunk_data = chunk.get("data", None)

                # 处理调试类型消息（新增）
                if chunk_type == "debug":
                    # 调试信息，可以选择发送或忽略
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {
                                "type": "debug",
                                "node": chunk.get("node", "unknown"),
                                "message_type": chunk.get("message_type", "unknown"),
                            },
                            ensure_ascii=False,
                        ),
                    }
                elif chunk_type == "tool_call":
                    if isinstance(chunk_data, dict):
                        tool_events.append(chunk_data)
                    # 发送工具调用事件（可选，前端可以显示工具调用状态）
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "tool_call", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "search_results":
                    # 发送检索结果（可选，前端可以忽略）
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "search_results", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "content":
                    full_response += chunk_data or ""
                    # 发送内容块 - 关键：data 必须是 JSON 字符串
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "content", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "complete":
                    complete_data = chunk_data if isinstance(chunk_data, dict) else {}
                    if not full_response:
                        full_response = str(complete_data.get("answer", ""))
                    complete_tool_calls = complete_data.get("tool_calls", [])
                    if isinstance(complete_tool_calls, list):
                        tool_events = cast(list[dict[str, object]], complete_tool_calls)
                    conversation_repository.save_chat_exchange(
                        request.id,
                        request.question,
                        full_response,
                    )
                    chat_tool_event_repository.append_events(
                        request.id,
                        exchange_id=exchange_id,
                        events=cast(list[dict[str, Any]], tool_events),
                    )
                    # 发送完成信号
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "done", "data": chunk_data}, ensure_ascii=False
                        ),
                    }
                elif chunk_type == "error":
                    # 发送错误信息
                    yield {
                        "event": "message",
                        "data": json.dumps(
                            {"type": "error", "data": str(chunk_data)}, ensure_ascii=False
                        ),
                    }

            logger.info(f"[会话 {request.id}] 流式对话完成")

        except Exception as e:
            logger.error(f"流式对话接口错误: {e}")
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "data": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/clear", response_model=ApiResponse)
async def clear_session(
    request: ClearRequest,
    _principal: Principal = Depends(require_capability("chat:use")),
):
    """清空会话历史

    Args:
        request: 清空请求

    Returns:
        操作结果
    """
    try:
        rag_agent_service = service_container.get_rag_agent_service()
        success = rag_agent_service.clear_session(request.session_id)
        persistent_deleted = conversation_repository.delete_session(request.session_id)
        logger.info(f"清空会话: {request.session_id}, 结果: {success}")

        return ApiResponse(
            status="success" if (success or persistent_deleted) else "error",
            message="会话已清空" if (success or persistent_deleted) else "清空会话失败",
            data=None,
        )

    except Exception as e:
        logger.error(f"清空会话错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/chat/sessions")
async def list_sessions(
    _principal: Principal = Depends(require_capability("chat:read")),
):
    """列出已持久化的会话摘要。"""
    try:
        sessions = conversation_repository.list_sessions()
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": sessions,
            },
        )
    except Exception as e:
        logger.error(f"获取会话列表错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/chat/session/{session_id}", response_model=SessionInfoResponse)
async def get_session_info(
    session_id: str,
    _principal: Principal = Depends(require_capability("chat:read")),
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
            rag_agent_service = service_container.get_rag_agent_service()
            history = rag_agent_service.get_session_history(session_id)

        return SessionInfoResponse(
            session_id=session_id, message_count=len(history), history=history
        )

    except Exception as e:
        logger.error(f"获取会话信息错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/chat/session/{session_id}/tool-events")
async def get_session_tool_events(
    session_id: str,
    _principal: Principal = Depends(require_capability("chat:read")),
):
    """查询会话工具调用事件。"""
    try:
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "message": "success",
                "data": chat_tool_event_repository.list_events(session_id),
            },
        )
    except Exception as e:
        logger.error(f"获取工具事件错误: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
