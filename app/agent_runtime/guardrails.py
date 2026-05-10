"""Input guardrails for the Native Agent runtime."""

from __future__ import annotations


def sanitize_goal(goal: str, *, max_length: int = 2000) -> str:
    """Strip, truncate, and validate agent goal input.

    Raises ``ValueError`` when the goal is empty after stripping.
    """
    if not isinstance(goal, str):
        raise ValueError("Goal must be a string.")
    cleaned = goal.strip()
    if not cleaned:
        raise ValueError("Goal must not be empty.")
    # Remove control characters except newlines and tabs
    cleaned = "".join(ch for ch in cleaned if ch in ("\n", "\t") or (ord(ch) >= 32))
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned
