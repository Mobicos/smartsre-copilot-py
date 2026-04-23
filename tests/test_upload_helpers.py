from __future__ import annotations

import pytest

from app.api.file import ALLOWED_EXTENSIONS, MAX_FILE_SIZE, _get_file_extension, _sanitize_filename


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("../runbook.md", ".._runbook.md"),
        (r"windows\path\ops guide.TXT", "windows_path_ops_guide.TXT"),
        ('bad:name*with?chars".md', "bad_name_with_chars_.md"),
    ],
)
def test_sanitize_filename_removes_path_and_shell_separators(filename: str, expected: str):
    assert _sanitize_filename(filename) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("ops.md", "md"),
        ("OPS.TXT", "txt"),
        ("archive.tar.gz", "gz"),
        ("README", ""),
    ],
)
def test_get_file_extension_normalizes_case(filename: str, expected: str):
    assert _get_file_extension(filename) == expected


def test_upload_policy_limits_supported_file_types_and_size():
    assert set(ALLOWED_EXTENSIONS) == {"md", "txt"}
    assert MAX_FILE_SIZE == 10 * 1024 * 1024
