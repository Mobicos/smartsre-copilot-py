from __future__ import annotations

from pathlib import Path

TEXT_PATHS = [
    Path("README.md"),
    Path("README.zh-CN.md"),
    Path("Makefile"),
    Path("pyproject.toml"),
    Path("AGENTS.md"),
    Path("PLAN.md"),
    *Path("app").rglob("*.py"),
    *Path("docs").rglob("*.md"),
]

MOJIBAKE_MARKERS = (
    "\ufffd",
    "\u00c3\u00a7\u00e2\u20ac\u2122",
    "\u00c3\u00a9\u00c2\u008d",
    "\u00c3\u00a6\u00c2\u00b6",
    "\u00e9\u008d",
    "\u00e7\u2019",
    "\u00e9\u008f",
    "\u00e6\u00be",
    "\u95b3\u30e6",
    "\u9234\u20ac",
)


def test_project_text_files_are_valid_utf8_and_not_mojibake():
    bad_files: list[str] = []

    for path in TEXT_PATHS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if any(marker in text for marker in MOJIBAKE_MARKERS):
            bad_files.append(str(path))

    assert bad_files == []
