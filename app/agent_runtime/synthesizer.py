"""Report synthesis for Native Agent runs."""

from __future__ import annotations

from app.agent_runtime.state import AgentRunState, KnowledgeContext


class ReportSynthesizer:
    """Build user-facing, evidence-driven reports from accumulated Agent state."""

    @staticmethod
    def build_report(state: AgentRunState) -> str:
        evidence = state.evidence_report_lines()
        evidence_text = (
            "\n".join(f"- {item}" for item in evidence)
            if evidence
            else "- 未采集到工具证据。"
        )
        knowledge_lines = state.knowledge_context.to_report_lines()
        knowledge_text = (
            "\n".join(knowledge_lines)
            if knowledge_lines
            else "- 未配置场景知识库。"
        )
        # Confirmed Facts: only successful evidence outputs
        confirmed_items = [item for item in state.evidence if item.status == "success"]
        if confirmed_items:
            confirmed_facts = "\n".join(
                f"- {item.tool_name}: {item.output}" for item in confirmed_items
            )
        else:
            confirmed_facts = "- 尚未确认任何事实。"
        # Executed Actions: tool name + execution status
        if state.evidence:
            executed_actions = "\n".join(
                f"- {item.tool_name}: {item.status}" for item in state.evidence
            )
        else:
            executed_actions = "- 未执行任何工具。"
        tool_failures = [
            item.to_report_line() for item in state.evidence if item.status not in {"success"}
        ]
        tool_failure_text = (
            "\n".join(f"- {item}" for item in tool_failures)
            if tool_failures
            else "- 未观测到工具失败、拒绝、超时或审批拦截。"
        )
        conclusion = (
            "已采集的证据支持上述观测结论，但最终根因仍需运维人员确认。"
            if evidence
            else "因未采集到证据，无法给出确定性根因判断。"
        )
        return (
            "# SmartSRE Agent 证据报告\n\n"
            f"## 目标\n{state.goal}\n\n"
            "## 成功标准\n"
            "- 仅使用场景允许的工具和知识上下文。\n"
            "- 保留可审计的证据、工具状态和不确定性。\n\n"
            f"## 已确认事实\n{confirmed_facts}\n\n"
            f"## 关键证据\n{evidence_text}\n\n"
            f"## 知识上下文\n{knowledge_text}\n\n"
            f"## 推理结论\n{conclusion}\n\n"
            "## 不确定性\n"
            "- 证据可能不完整、已过期或仅限于已配置的场景范围。\n\n"
            f"## 已执行操作\n{executed_actions}\n\n"
            f"## 未执行或被拦截的操作\n{tool_failure_text}\n\n"
            "## 恢复与降级\n"
            "- 需审批、被拒绝、超时或失败的工具结果不具备权威性。\n\n"
            "## 建议下一步\n"
            "- 审查引用的证据，针对未解决的不确定性执行后续检查。"
        )

    @staticmethod
    def build_bounded_report(
        state: AgentRunState,
        *,
        max_steps: int,
        executed_tools: list[str],
        skipped_tools: list[str],
    ) -> str:
        base_report = ReportSynthesizer.build_report(state)
        prefix = "# SmartSRE Agent 证据报告\n\n"
        body = base_report[len(prefix) :] if base_report.startswith(prefix) else base_report
        executed_text = ", ".join(executed_tools) if executed_tools else "无"
        skipped_text = ", ".join(skipped_tools) if skipped_tools else "无"
        return (
            f"{prefix}"
            "## 执行边界\n"
            f"- 最大工具步骤：{max_steps}\n"
            f"- 已执行工具：{executed_text}\n"
            f"- 已跳过工具：{skipped_text}\n\n"
            f"{body}"
        )

    @staticmethod
    def unavailable_report(
        goal: str,
        knowledge_context: KnowledgeContext | None = None,
    ) -> str:
        context = knowledge_context or KnowledgeContext.empty()
        knowledge_lines = context.to_report_lines()
        knowledge_text = (
            "\n".join(knowledge_lines)
            if knowledge_lines
            else "- 未配置场景知识库。"
        )
        return (
            "# SmartSRE Agent 证据报告\n\n"
            f"## 目标\n{goal}\n\n"
            f"## 知识上下文\n{knowledge_text}\n\n"
            "## 推理结论\n"
            "因未采集到可执行工具的证据，无法给出确定性根因判断。\n\n"
            "## 恢复与降级\n"
            "- 外部 MCP 工具不可用或场景无可执行工具。\n"
            "- 请配置日志、指标、告警或知识工具后重试。"
        )
