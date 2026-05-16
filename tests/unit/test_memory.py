"""Unit tests for cross-session memory subsystem (Phase 9 / T051-T052)."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.decision import (
    AgentDecisionState,
    AgentGoalContract,
)
from app.agent_runtime.loop import BoundedReActLoop, LoopBudget
from app.agent_runtime.memory_extractor import MemoryExtractor
from app.agent_runtime.memory_retriever import MemoryItem, MemoryRetriever


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeEmbeddingProvider:
    """Returns deterministic embeddings based on text content."""

    def __init__(self, dimension: int = 1024) -> None:
        self._dim = dimension
        self.calls: list[str] = []

    def embed_query(self, text: str) -> list[float]:
        self.calls.append(text)
        h = hash(text) % 1000
        return [float(h + i) / 1000.0 for i in range(self._dim)]


class _FakeMemoryStore:
    """In-memory memory store with pgvector search simulation."""

    def __init__(self) -> None:
        self.memories: list[dict[str, Any]] = []
        self._counter = 0

    def create_memory_with_embedding(
        self,
        *,
        workspace_id: str,
        run_id: str | None,
        conclusion_text: str,
        embedding: list[float],
        conclusion_type: str = "final_report",
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._counter += 1
        memory_id = f"mem-{self._counter:03d}"
        self.memories.append({
            "memory_id": memory_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "conclusion_text": conclusion_text,
            "conclusion_type": conclusion_type,
            "confidence": confidence,
            "validation_count": 0,
            "metadata": metadata or {},
            "embedding": embedding,
        })
        return memory_id

    def search_memory_vector(
        self,
        *,
        workspace_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for m in self.memories:
            if m["workspace_id"] != workspace_id:
                continue
            if not m.get("embedding"):
                continue
            sim = _fake_cosine(query_embedding, m["embedding"])
            if sim >= similarity_threshold:
                results.append({**m, "similarity": sim})
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    def increment_validation_count(
        self, *, memory_id: str, confidence_boost: float = 0.1
    ) -> dict[str, Any] | None:
        for m in self.memories:
            if m["memory_id"] == memory_id:
                m["validation_count"] += 1
                m["confidence"] = min(m["confidence"] + confidence_boost, 1.0)
                return dict(m)
        return None


def _fake_cosine(a: list[float], b: list[float]) -> float:
    """Simple cosine similarity for testing."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _make_fake_embedding(text: str, dim: int = 1024) -> list[float]:
    """Produce the same embedding _FakeEmbeddingProvider.embed_query would return."""
    h = hash(text) % 1000
    return [float(h + i) / 1000.0 for i in range(dim)]


def _make_state(
    goal: str = "diagnose OOM",
    workspace_id: str = "ws-1",
) -> AgentDecisionState:
    return AgentDecisionState(
        run_id="run-test-1",
        goal=AgentGoalContract(goal=goal, workspace_id=workspace_id),
    )


# ---------------------------------------------------------------------------
# MemoryRetriever tests (T051)
# ---------------------------------------------------------------------------


class TestMemoryRetriever:
    def test_high_similarity_returned(self):
        store = _FakeMemoryStore()
        # Store the embedding the fake provider will produce for the query
        query = "memory leak issue"
        store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-1",
            conclusion_text="OOM killer active, memory leak in worker",
            embedding=_make_fake_embedding(query),
            conclusion_type="root_cause",
            confidence=0.8,
        )
        retriever = MemoryRetriever(
            embedding_provider=_FakeEmbeddingProvider(),
            memory_store=store,
            top_k=5,
            similarity_threshold=0.5,
        )
        results = retriever.retrieve(workspace_id="ws-1", query=query)
        assert len(results) >= 1
        assert results[0].conclusion_type == "root_cause"

    def test_below_threshold_not_returned(self):
        store = _FakeMemoryStore()
        store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-1",
            conclusion_text="CPU spike on web server",
            embedding=[0.0] * 1024,
            conclusion_type="root_cause",
            confidence=0.8,
        )
        embedder = _FakeEmbeddingProvider()
        retriever = MemoryRetriever(
            embedding_provider=embedder,
            memory_store=store,
            similarity_threshold=0.99,
        )
        results = retriever.retrieve(
            workspace_id="ws-1",
            query="completely different topic",
        )
        assert results == []

    def test_empty_store_returns_empty(self):
        store = _FakeMemoryStore()
        embedder = _FakeEmbeddingProvider()
        retriever = MemoryRetriever(
            embedding_provider=embedder,
            memory_store=store,
        )
        results = retriever.retrieve(
            workspace_id="ws-1",
            query="anything",
        )
        assert results == []

    def test_embedding_failure_returns_empty(self):
        class _FailingEmbedder:
            def embed_query(self, text: str) -> list[float]:
                raise ConnectionError("embedding service down")

        store = _FakeMemoryStore()
        retriever = MemoryRetriever(
            embedding_provider=_FailingEmbedder(),
            memory_store=store,
        )
        results = retriever.retrieve(
            workspace_id="ws-1",
            query="test",
        )
        assert results == []

    def test_empty_query_returns_empty(self):
        store = _FakeMemoryStore()
        embedder = _FakeEmbeddingProvider()
        retriever = MemoryRetriever(
            embedding_provider=embedder,
            memory_store=store,
        )
        results = retriever.retrieve(workspace_id="ws-1", query="  ")
        assert results == []

    def test_format_for_context_empty(self):
        retriever = MemoryRetriever(
            embedding_provider=_FakeEmbeddingProvider(),
            memory_store=_FakeMemoryStore(),
        )
        assert retriever.format_for_context([]) == ""

    def test_format_for_context_with_memories(self):
        retriever = MemoryRetriever(
            embedding_provider=_FakeEmbeddingProvider(),
            memory_store=_FakeMemoryStore(),
        )
        memories = [
            MemoryItem(
                memory_id="m1",
                conclusion_text="OOM root cause is memory leak",
                conclusion_type="root_cause",
                confidence=0.85,
                validation_count=2,
                similarity=0.92,
            ),
        ]
        ctx = retriever.format_for_context(memories)
        assert "历史经验参考" in ctx
        assert "OOM" in ctx
        assert "已验证 2 次" in ctx
        assert "0.92" in ctx


# ---------------------------------------------------------------------------
# MemoryExtractor tests (T052)
# ---------------------------------------------------------------------------


class TestMemoryExtractor:
    def test_extract_root_cause_section(self):
        embedder = _FakeEmbeddingProvider()
        store = _FakeMemoryStore()
        extractor = MemoryExtractor(
            embedding_provider=embedder,
            memory_store=store,
        )
        report = (
            "# 诊断报告\n\n"
            "## 根因\n\n"
            "OOM killer 由内存泄漏触发，worker 进程占用 95% 内存。\n\n"
            "## 证据\n\n"
            "CPU 92%，内存 87%。\n\n"
            "## 解决方案\n\n"
            "重启服务并修复内存泄漏代码。"
        )
        stored = extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
            goal="diagnose OOM",
        )
        assert len(stored) == 3
        types = [s["conclusion_type"] for s in stored]
        assert "root_cause" in types
        assert "evidence" in types
        assert "solution" in types
        assert len(store.memories) == 3

    def test_extract_with_embedding(self):
        embedder = _FakeEmbeddingProvider()
        store = _FakeMemoryStore()
        extractor = MemoryExtractor(
            embedding_provider=embedder,
            memory_store=store,
        )
        report = "## 根因\n\n内存泄漏导致 OOM。"
        extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
        )
        assert len(store.memories) == 1
        assert len(store.memories[0]["embedding"]) == 1024

    def test_fallback_to_full_report_when_no_sections(self):
        embedder = _FakeEmbeddingProvider()
        store = _FakeMemoryStore()
        extractor = MemoryExtractor(
            embedding_provider=embedder,
            memory_store=store,
        )
        report = "This is a plain report without section headers."
        stored = extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
        )
        assert len(stored) == 1
        assert stored[0]["conclusion_type"] == "final_report"

    def test_short_sections_skipped(self):
        embedder = _FakeEmbeddingProvider()
        store = _FakeMemoryStore()
        extractor = MemoryExtractor(
            embedding_provider=embedder,
            memory_store=store,
        )
        report = "## 根因\n\n短。"
        stored = extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
        )
        # "短。" is < 10 chars, should be skipped
        assert len(stored) == 0

    def test_embedding_failure_still_stores(self):
        class _FailingEmbedder:
            def embed_query(self, text: str) -> list[float]:
                raise ConnectionError("down")

        store = _FakeMemoryStore()
        extractor = MemoryExtractor(
            embedding_provider=_FailingEmbedder(),
            memory_store=store,
        )
        report = "## 根因\n\nOOM killer active."
        stored = extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
        )
        assert len(stored) == 1
        assert store.memories[0]["embedding"] == []

    def test_goal_added_to_metadata(self):
        embedder = _FakeEmbeddingProvider()
        store = _FakeMemoryStore()
        extractor = MemoryExtractor(
            embedding_provider=embedder,
            memory_store=store,
        )
        report = "## 根因\n\n根因是数据库连接池耗尽。"
        extractor.extract_and_store(
            workspace_id="ws-1",
            run_id="run-1",
            final_report=report,
            goal="diagnose connection pool exhaustion",
        )
        assert store.memories[0]["metadata"]["goal"] == "diagnose connection pool exhaustion"


# ---------------------------------------------------------------------------
# Loop memory integration test (T049)
# ---------------------------------------------------------------------------


class TestLoopMemoryIntegration:
    def test_memory_retriever_called_on_first_step(self):
        store = _FakeMemoryStore()
        # Goal is "diagnose OOM" — store its exact embedding for perfect similarity
        store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-prev",
            conclusion_text="OOM root cause is memory leak in worker",
            embedding=_make_fake_embedding("diagnose OOM"),
            conclusion_type="root_cause",
            confidence=0.8,
        )
        retriever = MemoryRetriever(
            embedding_provider=_FakeEmbeddingProvider(),
            memory_store=store,
            similarity_threshold=0.5,
        )

        class _TerminalProvider:
            provider_name = "test"
            def decide(self, state):
                from app.agent_runtime.decision import AgentDecision, EvidenceAssessment
                return AgentDecision(
                    action_type="final_report",
                    selected_tool=None,
                    reasoning_summary="evidence sufficient",
                    evidence=EvidenceAssessment(quality="strong", summary="done"),
                    confidence=0.9,
                )

        loop = BoundedReActLoop(
            provider=_TerminalProvider(),
            memory_retriever=retriever,
        )
        state = _make_state(goal="diagnose OOM", workspace_id="ws-1")
        result = loop.run(state, LoopBudget(max_steps=3, max_time_seconds=30))

        assert result.termination_reason == "final_report"
        # Memory context should be injected into the state
        final_state = result.state
        assert "历史经验参考" in final_state.memory_context
        assert "OOM" in final_state.memory_context

    def test_no_memory_retriever_no_injection(self):
        class _TerminalProvider:
            provider_name = "test"
            def decide(self, state):
                from app.agent_runtime.decision import AgentDecision, EvidenceAssessment
                return AgentDecision(
                    action_type="final_report",
                    selected_tool=None,
                    reasoning_summary="done",
                    evidence=EvidenceAssessment(quality="strong"),
                    confidence=0.9,
                )

        loop = BoundedReActLoop(provider=_TerminalProvider())
        state = _make_state(goal="test", workspace_id="ws-1")
        result = loop.run(state, LoopBudget(max_steps=1, max_time_seconds=30))
        assert result.state.memory_context == ""

    def test_memory_retriever_failure_does_not_crash_loop(self):
        class _FailingRetriever:
            def retrieve(self, **kwargs):
                raise ConnectionError("down")
            def format_for_context(self, memories):
                return ""

        class _TerminalProvider:
            provider_name = "test"
            def decide(self, state):
                from app.agent_runtime.decision import AgentDecision, EvidenceAssessment
                return AgentDecision(
                    action_type="final_report",
                    selected_tool=None,
                    reasoning_summary="done",
                    evidence=EvidenceAssessment(quality="strong"),
                    confidence=0.9,
                )

        loop = BoundedReActLoop(
            provider=_TerminalProvider(),
            memory_retriever=_FailingRetriever(),
        )
        state = _make_state(goal="test", workspace_id="ws-1")
        result = loop.run(state, LoopBudget(max_steps=1, max_time_seconds=30))
        assert result.termination_reason == "final_report"


# ---------------------------------------------------------------------------
# MemoryValidator (T050) — via repository
# ---------------------------------------------------------------------------


class TestMemoryValidator:
    def test_increment_validation_count(self):
        store = _FakeMemoryStore()
        mem_id = store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-1",
            conclusion_text="test memory",
            embedding=[0.5] * 1024,
            confidence=0.6,
        )
        result = store.increment_validation_count(memory_id=mem_id, confidence_boost=0.1)
        assert result is not None
        assert result["validation_count"] == 1
        assert abs(result["confidence"] - 0.7) < 0.01

    def test_confidence_capped_at_one(self):
        store = _FakeMemoryStore()
        mem_id = store.create_memory_with_embedding(
            workspace_id="ws-1",
            run_id="run-1",
            conclusion_text="test",
            embedding=[0.5] * 1024,
            confidence=0.95,
        )
        store.increment_validation_count(memory_id=mem_id, confidence_boost=0.2)
        result = store.increment_validation_count(memory_id=mem_id, confidence_boost=0.2)
        assert result is not None
        assert result["confidence"] == 1.0

    def test_nonexistent_memory_returns_none(self):
        store = _FakeMemoryStore()
        result = store.increment_validation_count(memory_id="nonexistent")
        assert result is None
