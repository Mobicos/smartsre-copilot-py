"""Retrieve relevant cross-session memories for a new agent run."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    """Embedding generation interface."""

    def embed_query(self, text: str) -> list[float]: ...


class MemoryVectorSearch(Protocol):
    """Vector similarity search over stored memories."""

    def search_memory_vector(
        self,
        *,
        workspace_id: str,
        query_embedding: list[float],
        top_k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class MemoryItem:
    """A single retrieved memory with its similarity score."""

    memory_id: str
    conclusion_text: str
    conclusion_type: str
    confidence: float
    validation_count: int
    similarity: float
    run_id: str | None = None
    metadata: dict[str, Any] | None = None


class MemoryRetriever:
    """Retrieve similar historical conclusions for a new agent run.

    Usage::

        retriever = MemoryRetriever(
            embedding_provider=dashscope_embeddings,
            memory_store=agent_memory_repository,
        )
        memories = retriever.retrieve(
            workspace_id="ws-1",
            query="OOM killer active, high memory usage",
        )
        # → [MemoryItem(...), ...]
    """

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        memory_store: MemoryVectorSearch,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
    ) -> None:
        self._embedder = embedding_provider
        self._store = memory_store
        self._top_k = top_k
        self._similarity_threshold = similarity_threshold

    def retrieve(
        self,
        *,
        workspace_id: str,
        query: str,
        top_k: int | None = None,
        similarity_threshold: float | None = None,
    ) -> list[MemoryItem]:
        """Embed the query and retrieve similar memories via pgvector cosine search.

        Returns an empty list on embedding failure — never blocks the main flow.
        """
        if not query.strip():
            return []

        try:
            embedding = self._embedder.embed_query(query)
        except Exception:
            return []

        results = self._store.search_memory_vector(
            workspace_id=workspace_id,
            query_embedding=embedding,
            top_k=top_k or self._top_k,
            similarity_threshold=similarity_threshold or self._similarity_threshold,
        )

        return [
            MemoryItem(
                memory_id=r["memory_id"],
                conclusion_text=r["conclusion_text"],
                conclusion_type=r.get("conclusion_type", "final_report"),
                confidence=float(r.get("confidence", 0.5)),
                validation_count=int(r.get("validation_count", 0)),
                similarity=float(r.get("similarity", 0.0)),
                run_id=r.get("run_id"),
                metadata=r.get("metadata"),
            )
            for r in results
        ]

    def format_for_context(self, memories: list[MemoryItem]) -> str:
        """Format retrieved memories into a context string for the agent prompt."""
        if not memories:
            return ""

        lines = ["## 历史经验参考\n"]
        for i, mem in enumerate(memories, 1):
            boost = ""
            if mem.validation_count > 0:
                boost = f"（已验证 {mem.validation_count} 次）"
            confidence_pct = int(mem.confidence * 100)
            lines.append(
                f"{i}. [{mem.conclusion_type}] {mem.conclusion_text} "
                f"(置信度 {confidence_pct}%{boost}, 相似度 {mem.similarity:.2f})"
            )
        lines.append(
            "\n> 以上为历史相似诊断结论，仅供参考。请结合当前实际证据进行判断。"
        )
        return "\n".join(lines)
