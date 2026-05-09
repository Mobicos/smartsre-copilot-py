"""Shared constants for the Native Agent runtime."""

from __future__ import annotations

# Side-effect levels that force approval_required = True at every governance layer.
SIDE_EFFECTS_REQUIRING_APPROVAL = frozenset({"change", "destructive"})

# Evidence quality confidence scores used by the assessment pipeline.
CONFIDENCE_STRONG = 0.8
CONFIDENCE_PARTIAL = 0.4
CONFIDENCE_LOW = 0.2
CONFIDENCE_NONE = 0.0

# Runtime version identifier persisted in run metrics.
RUNTIME_VERSION = "native-agent-v1"

# Maximum characters kept from a tool output before truncation.
MAX_TOOL_OUTPUT_CHARS = 4000
