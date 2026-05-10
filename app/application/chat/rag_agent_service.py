"""RAG Agent 服务 - 基于 LangGraph 的智能代理

使用 langchain_qwq 的 ChatQwen 原生集成，
支持真正的流式输出和更好的模型适配。
"""

import json
import re
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, cast

from langchain.agents import create_agent
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_qwq import ChatQwen
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES, add_messages
from loguru import logger
from pydantic import SecretStr
from typing_extensions import TypedDict

from app.core.config import AppSettings
from app.infrastructure.tools import retrieve_knowledge, tool_registry

# 阿里千问大模型和langchain集成参考： https://docs.langchain.com/oss/python/integrations/chat/qwen
# 注意：需要配置环境变量 DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1 否则默认访问的是新加坡站点
# 同时也需要配置环境变量 DASHSCOPE_API_KEY=your_api_key


class AgentState(TypedDict):
    """Agent 状态"""

    messages: Annotated[Sequence[BaseMessage], add_messages]


@dataclass
class ChatQueryResult:
    """聊天查询结果。"""

    answer: str
    tool_events: list[dict[str, Any]]


def trim_messages_middleware(state: AgentState) -> dict[str, Any] | None:
    """
    修剪消息历史，只保留最近的几条消息以适应上下文窗口

    策略：
    - 保留第一条系统消息（System Message）
    - 保留最近的 6 条消息（3 轮对话）
    - 当消息少于等于 7 条时，不做修剪

    Args:
        state: Agent 状态

    Returns:
        包含修剪后消息的字典，如果无需修剪则返回 None
    """
    messages = state["messages"]

    # 如果消息数量较少，无需修剪
    if len(messages) <= 7:
        return None

    # 提取第一条系统消息
    first_msg = messages[0]

    # 保留最近的 6 条消息（确保包含完整的对话轮次）
    recent_messages = messages[-6:] if len(messages) % 2 == 0 else messages[-7:]

    # 构建新的消息列表
    new_messages = [first_msg] + list(recent_messages)

    logger.debug(f"修剪消息历史: {len(messages)} -> {len(new_messages)} 条")

    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *new_messages]}


class RagAgentService:
    """RAG Agent 服务 - 使用 LangGraph + ChatQwen 原生集成"""

    def __init__(
        self,
        settings: AppSettings | None = None,
        *,
        streaming: bool = True,
        checkpointer: BaseCheckpointSaver[str],
    ) -> None:
        """初始化 RAG Agent 服务

        Args:
            settings: AppSettings instance. If None, loads from environment.
            streaming: 是否启用流式输出，默认为 True
        """
        if settings is None:
            settings = AppSettings.from_env()
        self._settings = settings
        self.model_name = settings.rag_model
        self.streaming = streaming
        self.system_prompt = self._build_system_prompt()

        self.model = ChatQwen(
            model=self.model_name,
            api_key=SecretStr(settings.dashscope_api_key),
            temperature=0.7,
            streaming=streaming,
        )

        # MCP 客户端（延迟初始化，使用全局管理）
        self.mcp_tools: list = []

        # 持久化检查点（用于会话管理）
        self.checkpointer = checkpointer
        self.checkpoint_ns = "chat"

        # Agent 初始化（会在异步方法中完成）
        self.agent: Any | None = None
        self._agent_initialized = False

        logger.info(
            f"RAG Agent 服务初始化完成 (ChatQwen), model={self.model_name}, streaming={streaming}"
        )

    async def _initialize_agent(self):
        """异步初始化 Agent（包括 MCP 工具）"""
        if self._agent_initialized:
            return

        all_tools = await tool_registry.get_chat_tools()
        self.mcp_tools = [
            tool
            for tool in all_tools
            if getattr(tool, "name", "") not in {"retrieve_knowledge", "get_current_time"}
        ]

        self.agent = create_agent(
            self.model,
            tools=all_tools,
            checkpointer=self.checkpointer,
        )

        self._agent_initialized = True

        if all_tools:
            tool_names = [tool.name if hasattr(tool, "name") else str(tool) for tool in all_tools]
            logger.info(f"可用工具列表: {', '.join(tool_names)}")

    def _get_agent(self) -> Any:
        if self.agent is None:
            raise RuntimeError("RAG Agent has not been initialized")
        return self.agent

    def _build_system_prompt(self) -> str:
        """
        构建系统提示词

        注意：LangChain 框架会自动将工具信息传递给 LLM，
        因此系统提示词中无需列举具体的工具列表。

        Returns:
            str: 系统提示词
        """
        from textwrap import dedent

        return dedent("""
            你是一个专业的AI助手，能够使用多种工具来帮助用户解决问题。

            工作原则:
            1. 理解用户需求，选择合适的工具来完成任务
            2. 当需要获取实时信息或专业知识时，主动使用相关工具
            3. 基于工具返回的结果提供准确、专业的回答
            4. 如果工具无法提供足够信息，请诚实地告知用户

            回答要求:
            - 保持友好、专业的语气
            - 回答简洁明了，重点突出
            - 基于事实，不编造信息
            - 如有不确定的地方，明确说明

            请根据用户的问题，灵活使用可用工具，提供高质量的帮助。
        """).strip()

    async def query(
        self,
        question: str,
        session_id: str,
    ) -> ChatQueryResult:
        """
        非流式处理用户问题（一次性返回完整答案）

        Args:
            question: 用户问题
            session_id: 会话ID（作为 thread_id）

        Returns:
            ChatQueryResult: 完整答案与工具事件
        """
        try:
            await self._initialize_agent()

            logger.info(f"[会话 {session_id}] RAG Agent 收到查询（非流式）: {question}")

            # 构建消息列表（系统提示 + 用户问题）
            messages = [SystemMessage(content=self.system_prompt), HumanMessage(content=question)]

            # 构建 Agent 输入
            agent_input = {"messages": messages}

            # 配置 thread_id（用于会话持久化）
            config_dict = {
                "configurable": {
                    "thread_id": session_id,
                    "checkpoint_ns": self.checkpoint_ns,
                },
                "recursion_limit": self._settings.chat_recursion_limit,
            }

            result = await self._get_agent().ainvoke(
                input=agent_input,
                config=config_dict,
            )

            # 提取最终答案
            messages_result = result.get("messages", [])
            if messages_result:
                last_message = messages_result[-1]
                answer = (
                    last_message.content if hasattr(last_message, "content") else str(last_message)
                )

                tool_events = self._extract_tool_events_from_messages(messages_result)
                fallback_tool_event = self._extract_text_tool_code_event(answer)
                if fallback_tool_event is not None:
                    answer = await self._answer_from_text_tool_code(
                        question,
                        fallback_tool_event,
                    )
                    tool_events.append(fallback_tool_event)
                if tool_events:
                    logger.info(
                        f"[会话 {session_id}] Agent 调用了工具: "
                        f"{[event['toolName'] for event in tool_events]}"
                    )

                logger.info(f"[会话 {session_id}] RAG Agent 查询完成（非流式）")
                return ChatQueryResult(answer=answer, tool_events=tool_events)

            logger.warning(f"[会话 {session_id}] Agent 返回结果为空")
            return ChatQueryResult(answer="", tool_events=[])

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（非流式）: {e}")
            raise

    def _extract_text_tool_code_event(self, answer: str) -> dict[str, Any] | None:
        """Parse Qwen-style text tool code when native tool calling is not emitted."""
        match = re.search(r"<tool_code>\s*(\{.*?\})\s*</tool_code>", answer, re.DOTALL)
        if match is None:
            return None

        try:
            tool_call = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

        tool_name = str(tool_call.get("name", ""))
        if tool_name != "retrieve_knowledge":
            return None

        arguments = tool_call.get("arguments")
        if not isinstance(arguments, dict):
            return None

        query = str(arguments.get("query", "")).strip()
        if not query:
            return None

        logger.warning("Detected text-form retrieve_knowledge tool call; executing fallback")
        return {
            "toolName": tool_name,
            "eventType": "call",
            "status": "fallback",
            "payload": {"query": query},
        }

    async def _answer_from_text_tool_code(
        self,
        question: str,
        tool_event: dict[str, Any],
    ) -> str:
        """Execute a text-form knowledge tool call and synthesize a user-facing answer."""
        payload = tool_event.get("payload")
        query = str(payload.get("query", "")) if isinstance(payload, dict) else ""
        context = await retrieve_knowledge.ainvoke({"query": query})
        context_text = context[0] if isinstance(context, tuple) else str(context)

        response = await self.model.ainvoke(
            [
                SystemMessage(
                    content=(
                        "Answer the user using only the provided knowledge base context. "
                        "Do not include tool code or JSON."
                    )
                ),
                HumanMessage(
                    content=(
                        f"User question:\n{question}\n\n"
                        f"Knowledge base context:\n{context_text}\n\n"
                        "Return a concise answer."
                    )
                ),
            ]
        )
        content = response.content if hasattr(response, "content") else str(response)
        return content if isinstance(content, str) else str(content)

    async def query_stream(
        self,
        question: str,
        session_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        流式处理用户问题（逐步返回答案片段）

        Args:
            question: 用户问题
            session_id: 会话ID（作为 thread_id）

        Yields:
            Dict[str, Any]: 包含流式数据的字典
                - type: "content" | "tool_call" | "complete" | "error"
                - data: 具体内容
        """
        try:
            await self._initialize_agent()
            full_response = ""
            tool_events: list[dict[str, Any]] = []
            seen_signatures: set[str] = set()

            logger.info(f"[会话 {session_id}] RAG Agent 收到查询（流式）: {question}")

            # 构建消息列表（系统提示 + 用户问题）
            messages = [SystemMessage(content=self.system_prompt), HumanMessage(content=question)]

            # 构建 Agent 输入
            agent_input = {"messages": messages}

            # 配置 thread_id（用于会话持久化）
            config_dict = {
                "configurable": {
                    "thread_id": session_id,
                    "checkpoint_ns": self.checkpoint_ns,
                },
                "recursion_limit": self._settings.chat_recursion_limit,
            }

            async for token, metadata in self._get_agent().astream(
                input=agent_input,
                config=config_dict,
                stream_mode="messages",
            ):
                node_name = (
                    metadata.get("langgraph_node", "unknown")
                    if isinstance(metadata, dict)
                    else "unknown"
                )
                message_type = type(token).__name__
                extracted_tool_events = self._extract_tool_events_from_token(
                    token,
                    seen_signatures=seen_signatures,
                )
                for tool_event in extracted_tool_events:
                    tool_events.append(tool_event)
                    yield {
                        "type": "tool_call",
                        "data": tool_event,
                        "node": node_name,
                    }

                if message_type in ("AIMessage", "AIMessageChunk"):
                    content_blocks = getattr(token, "content_blocks", None)
                    raw_content = getattr(token, "content", None)

                    if content_blocks and isinstance(content_blocks, list):
                        for block in content_blocks:
                            if isinstance(block, dict) and block.get("type") == "text":
                                text_content = block.get("text", "")
                                if text_content:
                                    full_response += text_content
                                    yield {
                                        "type": "content",
                                        "data": text_content,
                                        "node": node_name,
                                    }
                    elif raw_content and isinstance(raw_content, str):
                        # Fallback: use content attribute directly when content_blocks is empty
                        full_response += raw_content
                        yield {
                            "type": "content",
                            "data": raw_content,
                            "node": node_name,
                        }

            logger.info(f"[会话 {session_id}] RAG Agent 查询完成（流式）")
            yield {
                "type": "complete",
                "data": {"answer": full_response, "tool_calls": tool_events},
            }

        except Exception as e:
            logger.error(f"[会话 {session_id}] RAG Agent 查询失败（流式）: {e}")
            yield {"type": "error", "data": str(e)}
            raise

    def get_session_history(self, session_id: str) -> list:
        """
        获取会话历史（从持久化 checkpointer 中读取）

        Args:
            session_id: 会话ID（即 thread_id）

        Returns:
            list: 消息历史列表 [{"role": "user|assistant", "content": "...", "timestamp": "..."}]
        """
        try:
            # 使用 checkpointer 的 get 方法获取最新的检查点
            # Read the latest checkpoint for this thread.
            config = {
                "configurable": {
                    "thread_id": session_id,
                    "checkpoint_ns": self.checkpoint_ns,
                }
            }
            checkpoint = self.checkpointer.get(cast(Any, config))

            if not checkpoint:
                logger.info(f"No session history found: {session_id}, message count: 0")
                return []

            checkpoint_data = cast(dict[str, Any], checkpoint)
            messages = checkpoint_data.get("channel_values", {}).get("messages", [])

            # 转换为前端需要的格式
            history = []
            for msg in messages:
                # 跳过系统消息
                if isinstance(msg, SystemMessage):
                    continue

                role = "user" if isinstance(msg, HumanMessage) else "assistant"
                content = msg.content if hasattr(msg, "content") else str(msg)

                # 提取时间戳（如果有的话）
                timestamp = getattr(msg, "timestamp", None)
                if timestamp:
                    history.append({"role": role, "content": content, "timestamp": timestamp})
                else:
                    from datetime import datetime

                    history.append(
                        {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
                    )

            logger.info(f"获取会话历史: {session_id}, 消息数量: {len(history)}")
            return history

        except Exception as e:
            logger.error(f"获取会话历史失败: {session_id}, 错误: {e}")
            return []

    def clear_session(self, session_id: str) -> bool:
        """
        清空会话历史（从持久化 checkpointer 中删除）

        Args:
            session_id: 会话ID（即 thread_id）

        Returns:
            bool: 是否成功
        """
        try:
            if hasattr(self.checkpointer, "delete_namespace"):
                self.checkpointer.delete_namespace(session_id, self.checkpoint_ns)
            else:
                self.checkpointer.delete_thread(session_id)

            logger.info(f"已清除会话历史: {session_id}")
            return True

        except Exception as e:
            logger.error(f"清空会话历史失败: {session_id}, 错误: {e}")
            return False

    async def cleanup(self):
        """清理资源"""
        try:
            logger.info("清理 RAG Agent 服务资源...")
            # MCP 客户端由全局管理器统一管理，无需手动清理
            logger.info("RAG Agent 服务资源已清理")
        except Exception as e:
            logger.error(f"清理资源失败: {e}")

    def _extract_tool_events_from_messages(
        self,
        messages: Sequence[BaseMessage],
    ) -> list[dict[str, Any]]:
        """从消息列表中提取去重后的工具调用事件。"""
        events: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()

        for message in messages:
            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                continue
            events.extend(self._normalize_tool_calls(tool_calls, seen_signatures))

        return events

    def _extract_tool_events_from_token(
        self,
        token: Any,
        *,
        seen_signatures: set[str],
    ) -> list[dict[str, Any]]:
        """从流式 token 中提取工具调用事件。"""
        tool_calls = getattr(token, "tool_calls", None)
        if tool_calls:
            return self._normalize_tool_calls(tool_calls, seen_signatures)

        content_blocks = getattr(token, "content_blocks", None)
        if not isinstance(content_blocks, list):
            return []

        tool_calls_from_blocks: list[dict[str, Any]] = []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in {"tool_call", "server_tool_call"}:
                continue
            tool_calls_from_blocks.append(
                {
                    "id": block.get("id"),
                    "name": block.get("name", "unknown"),
                    "args": block.get("args") or block.get("input") or {},
                }
            )

        return self._normalize_tool_calls(tool_calls_from_blocks, seen_signatures)

    def _normalize_tool_calls(
        self,
        tool_calls: Sequence[dict[str, Any]],
        seen_signatures: set[str],
    ) -> list[dict[str, Any]]:
        """归一化工具调用并去重。"""
        normalized: list[dict[str, Any]] = []

        for tool_call in tool_calls:
            tool_name = str(tool_call.get("name", "unknown"))
            payload = {
                "toolCallId": tool_call.get("id"),
                "args": tool_call.get("args", {}),
            }
            signature = json.dumps(
                {
                    "toolName": tool_name,
                    "toolCallId": payload["toolCallId"],
                    "args": payload["args"],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if signature in seen_signatures:
                continue

            seen_signatures.add(signature)
            normalized.append(
                {
                    "toolName": tool_name,
                    "eventType": "call",
                    "payload": payload,
                }
            )

        return normalized
