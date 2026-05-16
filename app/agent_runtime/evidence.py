"""Evidence quality assessment for Native Agent decisions."""

from __future__ import annotations

from app.agent_runtime.constants import (
    CONFIDENCE_LOW,
    CONFIDENCE_NONE,
    CONFIDENCE_PARTIAL,
    CONFIDENCE_STRONG,
)
from app.agent_runtime.decision import EvidenceAssessment
from app.agent_runtime.state import EvidenceItem

CONFIDENCE_WEAK = 0.35


class EvidenceAssessor:
    """Classify tool evidence before the runtime writes conclusions."""

    def assess(self, evidence: EvidenceItem) -> EvidenceAssessment:
        citation = {
            "source": "tool",
            "tool_name": evidence.tool_name,
            "status": evidence.status,
        }
        if evidence.status in {"timeout", "disabled", "forbidden"} or evidence.error:
            return EvidenceAssessment(
                quality="error",
                summary=f"{evidence.tool_name} 返回 {evidence.status}：{evidence.error or '无详情'}",
                citations=[citation],
                confidence=CONFIDENCE_NONE,
            )
        if evidence.status == "approval_required":
            return EvidenceAssessment(
                quality="partial",
                summary=f"{evidence.tool_name} 需要审批才能采集证据。",
                citations=[citation],
                confidence=CONFIDENCE_LOW,
            )
        if evidence.status == "partial":
            return EvidenceAssessment(
                quality="partial",
                summary=f"{evidence.tool_name} 返回了部分证据。",
                citations=[citation],
                confidence=CONFIDENCE_PARTIAL,
            )
        if evidence.status == "weak":
            return EvidenceAssessment(
                quality="weak",
                summary=f"{evidence.tool_name} 返回了弱证据，需要继续验证。",
                citations=[citation],
                confidence=CONFIDENCE_WEAK,
            )
        if _is_empty_output(evidence.output):
            return EvidenceAssessment(
                quality="empty",
                summary=f"{evidence.tool_name} 未返回可用证据。",
                citations=[citation],
                confidence=CONFIDENCE_NONE,
            )
        return EvidenceAssessment(
            quality="strong",
            summary=f"{evidence.tool_name} 返回了可用证据。",
            citations=[citation],
            confidence=CONFIDENCE_STRONG,
        )

    def assess_many(self, evidence_items: list[EvidenceItem]) -> EvidenceAssessment:
        if not evidence_items:
            return EvidenceAssessment(
                quality="empty",
                summary="未采集到任何证据。",
                confidence=CONFIDENCE_NONE,
            )
        conflict = _root_cause_conflict(evidence_items)
        if conflict is not None:
            return EvidenceAssessment(
                quality="conflicting",
                summary="多个工具返回了相互冲突的根因候选，需要继续验证或人工交接。",
                citations=conflict,
                confidence=CONFIDENCE_NONE,
            )
        assessments = [self.assess(item) for item in evidence_items]
        strong = next((item for item in assessments if item.quality == "strong"), None)
        if strong is not None:
            return strong
        partial = next((item for item in assessments if item.quality == "partial"), None)
        if partial is not None:
            return partial
        weak = next((item for item in assessments if item.quality == "weak"), None)
        if weak is not None:
            return weak
        error = next((item for item in assessments if item.quality == "error"), None)
        return error or assessments[0]

    def handoff_reason(self, assessment: EvidenceAssessment) -> str:
        if assessment.quality == "empty":
            return "insufficient_evidence"
        if assessment.quality == "conflicting":
            return "conflicting_evidence"
        return "evidence_error"


def _is_empty_output(output: object) -> bool:
    if output is None or output == "":
        return True
    if isinstance(output, (list, tuple, set, dict)) and not output:
        return True
    return False


def _root_cause_conflict(evidence_items: list[EvidenceItem]) -> list[dict[str, str]] | None:
    root_causes: dict[str, list[str]] = {}
    for item in evidence_items:
        if not isinstance(item.output, dict):
            continue
        root_cause = item.output.get("root_cause")
        if not root_cause:
            continue
        normalized = str(root_cause).strip().lower()
        if not normalized:
            continue
        root_causes.setdefault(normalized, []).append(item.tool_name)

    if len(root_causes) <= 1:
        return None

    return [
        {
            "source": "tool",
            "tool_name": tool_name,
            "root_cause": root_cause,
        }
        for root_cause, tool_names in root_causes.items()
        for tool_name in tool_names
    ]
