"""Integration tests for the feedback → badcase → FAQ knowledge loop (Phase 6 / T034).

These tests use lightweight mocks for repositories to avoid database
dependencies while still verifying the full orchestration flow through
NativeAgentApplicationService and BadcaseClusterer.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from app.application.badcase_service import (
    BadcaseClusterer,
    FAQCandidate,
    _char_bigram_jaccard,
)
from app.application.native_agent_application_service import (
    NativeAgentApplicationService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubFeedbackRepository:
    """In-memory feedback store for testing."""

    def __init__(self) -> None:
        self._feedbacks: dict[str, dict[str, Any]] = {}
        self._call_log: list[dict[str, Any]] = []

    def create_feedback(
        self,
        run_id: str,
        *,
        rating: str,
        comment: str | None = None,
        correction: str | None = None,
        badcase_flag: bool = False,
        original_report: str | None = None,
    ) -> str:
        feedback_id = f"fb-{len(self._feedbacks) + 1:03d}"
        self._feedbacks[feedback_id] = {
            "feedback_id": feedback_id,
            "run_id": run_id,
            "rating": rating,
            "comment": comment,
            "correction": correction,
            "badcase_flag": badcase_flag,
            "original_report": original_report,
            "review_status": "pending",
        }
        return feedback_id

    def list_badcases(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [fb for fb in self._feedbacks.values() if fb.get("badcase_flag")][:limit]

    def get_badcase(self, feedback_id: str) -> dict[str, Any] | None:
        fb = self._feedbacks.get(feedback_id)
        if fb and fb.get("badcase_flag"):
            return {**fb, "run": {"run_id": fb["run_id"], "goal": "diagnose memory"}}
        return None

    def review_badcase(
        self,
        feedback_id: str,
        *,
        review_status: str,
        review_note: str | None,
        reviewed_by: str | None,
    ) -> dict[str, Any] | None:
        fb = self._feedbacks.get(feedback_id)
        if fb is None or not fb.get("badcase_flag"):
            return None
        fb["review_status"] = review_status
        fb["review_note"] = review_note
        fb["reviewed_by"] = reviewed_by
        self._call_log.append(
            {"action": "review", "feedback_id": feedback_id, "status": review_status}
        )
        return dict(fb)

    def mark_badcase_knowledge_promotion(
        self,
        feedback_id: str,
        *,
        knowledge_status: str,
        knowledge_task_id: str,
        knowledge_filename: str,
    ) -> dict[str, Any] | None:
        fb = self._feedbacks.get(feedback_id)
        if fb is None or not fb.get("badcase_flag"):
            return None
        fb["knowledge_status"] = knowledge_status
        fb["knowledge_task_id"] = knowledge_task_id
        fb["knowledge_filename"] = knowledge_filename
        return dict(fb)


class _StubRunRepository:
    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return {
            "run_id": run_id,
            "workspace_id": "ws-1",
            "status": "completed",
            "goal": "diagnose high memory usage",
            "final_report": "Root cause: OOM killer active due to memory leak in worker.",
        }


class _StubMemoryRepository:
    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []

    def create_memory(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        conclusion_text: str,
        conclusion_type: str = "final_report",
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        memory_id = f"mem-{len(self.memories) + 1:03d}"
        self.memories.append(
            {
                "memory_id": memory_id,
                "workspace_id": workspace_id,
                "run_id": run_id,
                "conclusion_text": conclusion_text,
                "conclusion_type": conclusion_type,
                "confidence": confidence,
                "metadata": metadata or {},
            }
        )
        return memory_id


def _make_service(
    feedback_repo: _StubFeedbackRepository | None = None,
    run_repo: _StubRunRepository | None = None,
    memory_repo: _StubMemoryRepository | None = None,
) -> tuple[NativeAgentApplicationService, _StubFeedbackRepository, _StubMemoryRepository]:
    fb = feedback_repo or _StubFeedbackRepository()
    rr = run_repo or _StubRunRepository()
    mr = memory_repo or _StubMemoryRepository()

    service = NativeAgentApplicationService.__new__(NativeAgentApplicationService)
    service._agent_run_repository = rr
    service._agent_feedback_repository = fb
    service._agent_memory_repository = mr
    # Remaining fields not needed for feedback loop tests
    service._agent_runtime = MagicMock()
    service._tool_catalog = MagicMock()
    service._workspace_repository = MagicMock()
    service._scene_repository = MagicMock()
    service._tool_policy_repository = MagicMock()
    return service, fb, mr


def _submit_feedback(
    service: NativeAgentApplicationService,
    *,
    rating: str = "down",
    correction: str = "应该先检查内存泄漏，而不是重启服务",
) -> dict[str, Any] | None:
    return service.create_agent_feedback(
        "run-001",
        rating=rating,
        comment="operator correction",
        correction=correction,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCharBigramJaccard:
    def test_identical_texts_score_one(self):
        assert _char_bigram_jaccard("hello", "hello") == 1.0

    def test_empty_text_scores_zero(self):
        assert _char_bigram_jaccard("", "hello") == 0.0
        assert _char_bigram_jaccard("hello", "") == 0.0
        assert _char_bigram_jaccard("", "") == 0.0

    def test_single_char_texts_have_nonzero_overlap(self):
        # single-char fallback set contains the char itself
        assert _char_bigram_jaccard("a", "a") == 1.0
        assert _char_bigram_jaccard("a", "b") == 0.0

    def test_similar_chinese_texts_score_high(self):
        a = "应该先检查内存泄漏，而不是重启服务"
        b = "应该先检查内存泄漏问题，再考虑重启服务"
        score = _char_bigram_jaccard(a, b)
        assert score > 0.4  # significant overlap despite different phrasing

    def test_unrelated_texts_score_low(self):
        a = "应该检查CPU使用率"
        b = "重启服务解决内存问题"
        score = _char_bigram_jaccard(a, b)
        assert score < 0.3


class TestBadcaseClusterer:
    def test_empty_input_returns_no_clusters(self):
        assert BadcaseClusterer().cluster([]) == []

    def test_similar_corrections_form_single_cluster(self):
        corrections = [
            "应该先检查内存泄漏",
            "应该先检查内存泄漏问题",
            "应该先检查内存是否存在泄漏",
            "应该先排查内存泄漏",
            "应该先做内存泄漏检查",
        ]
        badcases = [
            {"feedback_id": f"fb-{i}", "correction": c, "review_status": "confirmed"}
            for i, c in enumerate(corrections, 1)
        ]
        clusterer = BadcaseClusterer(min_cluster_size=3)
        clusters = clusterer.cluster(badcases)
        assert len(clusters) >= 1
        assert any(c.size >= 3 for c in clusters)

    def test_unrelated_corrections_form_separate_clusters(self):
        badcases = [
            {"feedback_id": "fb-1", "correction": "应该先检查内存泄漏"},
            {"feedback_id": "fb-2", "correction": "应该先检查CPU使用率"},
            {"feedback_id": "fb-3", "correction": "应该先查看网络延迟"},
        ]
        clusterer = BadcaseClusterer(min_cluster_size=1)
        clusters = clusterer.cluster(badcases)
        assert len(clusters) == 3

    def test_cluster_with_no_correction_skipped(self):
        badcases = [
            {"feedback_id": "fb-1", "correction": None},
            {"feedback_id": "fb-2", "correction": ""},
        ]
        clusterer = BadcaseClusterer()
        assert clusterer.cluster(badcases) == []


class TestFAQCandidateGeneration:
    def _make_badcases(self, n: int, correction: str) -> list[dict[str, Any]]:
        return [
            {
                "feedback_id": f"fb-{i}",
                "correction": correction,
                "review_status": "confirmed",
                "run": {"goal": "diagnose OOM"},
            }
            for i in range(1, n + 1)
        ]

    def test_faq_candidate_generated_above_threshold(self):
        badcases = self._make_badcases(6, "应该先检查内存泄漏问题")
        clusterer = BadcaseClusterer(min_cluster_size=5)
        candidates = clusterer.generate_faq_candidates(badcases)
        assert len(candidates) == 1
        faq = candidates[0]
        assert isinstance(faq, FAQCandidate)
        assert len(faq.feedback_ids) == 6
        assert faq.title == "diagnose OOM"
        assert "内存泄漏" in faq.suggested_answer

    def test_no_faq_below_threshold(self):
        badcases = self._make_badcases(3, "应该先检查内存泄漏问题")
        clusterer = BadcaseClusterer(min_cluster_size=5)
        candidates = clusterer.generate_faq_candidates(badcases)
        assert len(candidates) == 0

    def test_faq_title_uses_most_common_goal(self):
        badcases = [
            {"feedback_id": "fb-1", "correction": "fix A", "run": {"goal": "diagnose OOM"}},
            {"feedback_id": "fb-2", "correction": "fix A", "run": {"goal": "diagnose OOM"}},
            {"feedback_id": "fb-3", "correction": "fix A", "run": {"goal": "diagnose OOM"}},
            {"feedback_id": "fb-4", "correction": "fix A", "run": {"goal": "check CPU"}},
            {"feedback_id": "fb-5", "correction": "fix A", "run": {"goal": "diagnose OOM"}},
        ]
        clusterer = BadcaseClusterer(min_cluster_size=5)
        candidates = clusterer.generate_faq_candidates(badcases)
        assert len(candidates) == 1
        assert candidates[0].title == "diagnose OOM"


class TestNativeAgentFAQWorkflow:
    def test_feedback_creates_badcase_flag(self):
        service, _, _ = _make_service()
        result = _submit_feedback(service, correction="根因是内存泄漏")
        assert result is not None
        assert result["badcase_flag"] is True

    def test_positive_rating_no_badcase_flag(self):
        service, _, _ = _make_service()
        result = _submit_feedback(service, rating="up", correction=None)
        assert result is not None
        assert result["badcase_flag"] is False

    def test_list_faq_candidates_empty_when_few_badcases(self):
        service, _, _ = _make_service()
        candidates = service.list_faq_candidates(min_cluster_size=5)
        assert candidates == []

    def test_list_faq_candidates_groups_similar_corrections(self):
        service, fb_repo, _ = _make_service()
        # Create 6 confirmed badcases with similar corrections
        for _ in range(1, 7):
            fb_repo.create_feedback(
                "run-001",
                rating="down",
                correction="应该先检查内存泄漏问题",
                badcase_flag=True,
            )
        for fb in fb_repo._feedbacks.values():
            fb["review_status"] = "confirmed"

        candidates = service.list_faq_candidates(min_cluster_size=5)
        assert len(candidates) == 1
        assert len(candidates[0]["feedback_ids"]) == 6

    def test_confirm_faq_candidate_sets_review_status(self):
        service, fb_repo, _ = _make_service()
        feedback_ids = []
        for _ in range(1, 6):
            fid = fb_repo.create_feedback(
                "run-001",
                rating="down",
                correction="应该先检查内存泄漏",
                badcase_flag=True,
            )
            feedback_ids.append(fid)
        for fb in fb_repo._feedbacks.values():
            fb["review_status"] = "confirmed"

        result = service.confirm_faq_candidate(
            feedback_ids=feedback_ids,
            reviewed_by="operator-1",
        )
        assert result["status"] == "confirmed"
        assert result["size"] == 5
        # All feedbacks should now have review_status="confirmed"
        for fid in feedback_ids:
            assert fb_repo._feedbacks[fid]["review_status"] == "confirmed"


class TestFeedbackCorrectionInMemory:
    def test_correction_written_to_memory_repository(self):
        service, _, memory_repo = _make_service()
        _submit_feedback(service, correction="根因是内存泄漏")
        assert len(memory_repo.memories) == 1
        mem = memory_repo.memories[0]
        assert mem["conclusion_text"] == "根因是内存泄漏"
        assert mem["conclusion_type"] == "correction"
        assert mem["metadata"]["source"] == "feedback"
