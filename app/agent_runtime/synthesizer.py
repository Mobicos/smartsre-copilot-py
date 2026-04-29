"""Report synthesis for Native Agent runs."""

from __future__ import annotations

from app.agent_runtime.state import AgentRunState, KnowledgeContext


class ReportSynthesizer:
    """Build user-facing reports from accumulated Agent state."""

    @staticmethod
    def build_report(state: AgentRunState) -> str:
        evidence = state.evidence_report_lines()
        evidence_text = (
            "\n".join(f"- {item}" for item in evidence) if evidence else "- 暂无工具证据"
        )
        knowledge_lines = state.knowledge_context.to_report_lines()
        knowledge_text = "\n".join(knowledge_lines) if knowledge_lines else "- 当前场景未配置知识库"
        return (
            "# SmartSRE Agent 诊断报告\n\n"
            f"## 目标\n{state.goal}\n\n"
            f"## 初始假设\n{state.hypothesis.summary}\n\n"
            f"## 知识上下文\n{knowledge_text}\n\n"
            f"## 证据\n{evidence_text}\n\n"
            "## 结论\n以上结论基于当前场景已授权工具的返回结果生成。"
        )

    @staticmethod
    def unavailable_report(
        goal: str,
        knowledge_context: KnowledgeContext | None = None,
    ) -> str:
        context = knowledge_context or KnowledgeContext.empty()
        knowledge_lines = context.to_report_lines()
        knowledge_text = "\n".join(knowledge_lines) if knowledge_lines else "- 当前场景未配置知识库"
        return (
            "# SmartSRE Agent 诊断报告\n\n"
            f"## 目标\n{goal}\n\n"
            f"## 知识上下文\n{knowledge_text}\n\n"
            "## 结论\n外部 MCP 工具不可用或当前场景未配置可执行工具，"
            "Agent 未编造工具名称或诊断证据。请先在场景中关联日志、监控或告警工具后重试。"
        )
