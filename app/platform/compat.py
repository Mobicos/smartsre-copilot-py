"""Platform compatibility shims for deterministic local tooling."""

from __future__ import annotations

import os
import platform
import sys


def stabilize_windows_platform_detection() -> None:
    """Avoid slow or hanging WMI calls in import-time platform checks."""
    if not sys.platform.startswith("win"):
        return

    architecture = os.environ.get("PROCESSOR_ARCHITECTURE") or "AMD64"
    platform.machine = lambda: architecture
