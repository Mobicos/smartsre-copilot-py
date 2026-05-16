from __future__ import annotations

from app.agent_runtime.evidence import EvidenceAssessor
from app.agent_runtime.state import EvidenceItem


def test_evidence_assessor_classifies_empty_outputs_as_empty():
    assessor = EvidenceAssessor()

    assert assessor.assess(EvidenceItem("SearchLog", "success", output=[])).quality == "empty"
    assert assessor.assess(EvidenceItem("SearchMetric", "success", output={})).quality == "empty"


def test_evidence_assessor_preserves_weak_status():
    assessment = EvidenceAssessor().assess(
        EvidenceItem(
            tool_name="SearchLog",
            status="weak",
            output={"message": "matched old logs only"},
        )
    )

    assert assessment.quality == "weak"
    assert 0 < assessment.confidence < 0.5


def test_evidence_assessor_detects_conflicting_root_causes():
    assessment = EvidenceAssessor().assess_many(
        [
            EvidenceItem(
                tool_name="SearchLog",
                status="success",
                output={"root_cause": "database saturation"},
            ),
            EvidenceItem(
                tool_name="SearchMetric",
                status="success",
                output={"root_cause": "cache miss storm"},
            ),
        ]
    )

    assert assessment.quality == "conflicting"
    assert assessment.confidence == 0
    assert {citation["tool_name"] for citation in assessment.citations} == {
        "SearchLog",
        "SearchMetric",
    }
