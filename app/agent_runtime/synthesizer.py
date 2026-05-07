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
            else "- No tool evidence was collected."
        )
        knowledge_lines = state.knowledge_context.to_report_lines()
        knowledge_text = (
            "\n".join(knowledge_lines)
            if knowledge_lines
            else "- No scene knowledge base is configured."
        )
        tool_failures = [
            item.to_report_line() for item in state.evidence if item.status not in {"success"}
        ]
        tool_failure_text = (
            "\n".join(f"- {item}" for item in tool_failures)
            if tool_failures
            else "- No tool failure, denial, timeout, or approval block was observed."
        )
        confirmed_facts = evidence_text if evidence else "- No facts are confirmed yet."
        conclusion = (
            "The collected evidence supports the observations above, but the final root "
            "cause still requires operator confirmation."
            if evidence
            else "No deterministic root cause is claimed because no evidence was collected."
        )
        return (
            "# SmartSRE Agent Evidence Report\n\n"
            f"## Goal\n{state.goal}\n\n"
            "## Success Criteria\n"
            "- Use only scene-approved tools and knowledge context.\n"
            "- Preserve auditable evidence, tool status, and uncertainty.\n\n"
            f"## Confirmed Facts\n{confirmed_facts}\n\n"
            f"## Key Evidence\n{evidence_text}\n\n"
            f"## Knowledge Context\n{knowledge_text}\n\n"
            f"## Inference Conclusion\n{conclusion}\n\n"
            "## Uncertainty\n"
            "- Evidence can be incomplete, stale, or scoped to the configured scene.\n\n"
            f"## Executed Actions\n{evidence_text}\n\n"
            f"## Unexecuted Or Blocked Actions\n{tool_failure_text}\n\n"
            "## Recovery And Degradation\n"
            "- Approval-required, denied, timed-out, or failed tools are non-authoritative.\n\n"
            "## Recommended Next Step\n"
            "- Review cited evidence and run targeted follow-up checks for unresolved uncertainty."
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
        prefix = "# SmartSRE Agent Evidence Report\n\n"
        body = base_report[len(prefix) :] if base_report.startswith(prefix) else base_report
        executed_text = ", ".join(executed_tools) if executed_tools else "none"
        skipped_text = ", ".join(skipped_tools) if skipped_tools else "none"
        return (
            f"{prefix}"
            "## Execution Boundaries\n"
            f"- Maximum tool steps: {max_steps}\n"
            f"- Executed tools: {executed_text}\n"
            f"- Skipped tools: {skipped_text}\n\n"
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
            else "- No scene knowledge base is configured."
        )
        return (
            "# SmartSRE Agent Evidence Report\n\n"
            f"## Goal\n{goal}\n\n"
            f"## Knowledge Context\n{knowledge_text}\n\n"
            "## Inference Conclusion\n"
            "No deterministic root cause is claimed because no executable tool evidence "
            "was collected.\n\n"
            "## Recovery And Degradation\n"
            "- External MCP tools are unavailable or the scene has no executable tools.\n"
            "- å¤–éƒ¨ MCP å·¥å…·ä¸å¯ç”¨ or the scene has no executable tools.\n"
            "- Configure log, metric, alert, or knowledge tools before retrying."
        )
