from __future__ import annotations

from pathlib import Path

TEXT_PATHS = [
    Path("README.md"),
    Path("Makefile"),
    Path("pyproject.toml"),
    Path("AGENTS.md"),
    *Path("app").rglob("*.py"),
]

MOJIBAKE_MARKERS = (
    "\ufffd",
    "Ã",
    "Â",
    "ç’",
    "é",
    "æ¶",
    "î",
)


def test_project_text_files_are_valid_utf8_and_not_mojibake():
    bad_files: list[str] = []

    for path in TEXT_PATHS:
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            bad_files.append(str(path))

    assert bad_files == []
