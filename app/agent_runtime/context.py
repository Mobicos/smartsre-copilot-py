"""Knowledge context loading for Native Agent runs."""

from __future__ import annotations

from typing import Any

from app.agent_runtime.state import KnowledgeContext


class KnowledgeContextProvider:
    """Build scene-scoped knowledge context for the runtime."""

    @staticmethod
    def build_context(scene: dict[str, Any]) -> KnowledgeContext:
        knowledge_bases = [
            {
                "id": str(item["id"]),
                "name": str(item["name"]),
                "description": item.get("description"),
                "version": str(item.get("version") or "0.0.1"),
            }
            for item in scene.get("knowledge_bases", [])
        ]
        return KnowledgeContext(knowledge_bases=knowledge_bases)
