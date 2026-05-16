"""Extract key conclusions from a final report and store them as memories."""

from __future__ import annotations

import re
from typing import Any, Protocol


class EmbeddingProvider(Protocol):
    """Embedding generation interface."""

    def embed_query(self, text: str) -> list[float]: ...


class MemoryStore(Protocol):
    """Memory persistence interface."""

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
    ) -> str: ...


class MemoryExtractor:
    """Extract structured conclusions from a final report and persist them.

    Sections parsed from the report:
    - ``## 根因`` / ``## Root Cause`` → conclusion_type="root_cause"
    - ``## 证据`` / ``## Evidence`` → conclusion_type="evidence"
    - ``## 解决方案`` / ``## Solution`` → conclusion_type="solution"
    - Fallback: entire report → conclusion_type="final_report"
    """

    _SECTION_PATTERNS: list[tuple[str, str]] = [
        (r"^##\s*(?:根因|Root\s*Cause)[:\s]*(.*)", "root_cause"),
        (r"^##\s*(?:证据|Evidence)[:\s]*(.*)", "evidence"),
        (r"^##\s*(?:解决方案|Solution|建议|Recommendation)[:\s]*(.*)", "solution"),
    ]

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        memory_store: MemoryStore,
    ) -> None:
        self._embedder = embedding_provider
        self._store = memory_store

    def extract_and_store(
        self,
        *,
        workspace_id: str,
        run_id: str,
        final_report: str,
        goal: str = "",
    ) -> list[dict[str, Any]]:
        """Parse the final report, embed each conclusion, and store it."""
        sections = self._parse_sections(final_report)
        if not sections:
            sections = [("final_report", final_report.strip())]

        stored: list[dict[str, Any]] = []
        for conclusion_type, text in sections:
            if not text or len(text) < 10:
                continue
            truncated = text[:2000]
            try:
                embedding = self._embedder.embed_query(truncated)
            except Exception:
                embedding = []
            metadata: dict[str, Any] = {"source": "memory_extractor"}
            if goal:
                metadata["goal"] = goal

            confidence = self._section_confidence(conclusion_type)
            memory_id = self._store.create_memory_with_embedding(
                workspace_id=workspace_id,
                run_id=run_id,
                conclusion_text=truncated,
                embedding=embedding,
                conclusion_type=conclusion_type,
                confidence=confidence,
                metadata=metadata,
            )
            stored.append({
                "memory_id": memory_id,
                "conclusion_type": conclusion_type,
                "text_preview": truncated[:100],
            })

        return stored

    def _parse_sections(self, report: str) -> list[tuple[str, str]]:
        lines = report.split("\n")
        sections: list[tuple[str, str]] = []
        current_type: str | None = None
        current_lines: list[str] = []

        for line in lines:
            matched = False
            for pattern, ctype in self._SECTION_PATTERNS:
                if re.match(pattern, line, re.IGNORECASE):
                    if current_type and current_lines:
                        sections.append((current_type, "\n".join(current_lines).strip()))
                    current_type = ctype
                    current_lines = []
                    matched = True
                    break
            if not matched:
                if current_type is not None:
                    current_lines.append(line)

        if current_type and current_lines:
            sections.append((current_type, "\n".join(current_lines).strip()))

        return sections

    @staticmethod
    def _section_confidence(conclusion_type: str) -> float:
        return {
            "root_cause": 0.8,
            "evidence": 0.7,
            "solution": 0.75,
            "final_report": 0.5,
        }.get(conclusion_type, 0.5)
