from __future__ import annotations

import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.infrastructure.file_integrity import (  # noqa: E402
    FileIntegrityGuard,
    SourceFileChangedError,
)


def test_read_checked_returns_value_and_content_identity(tmp_path):
    path = tmp_path / "input.xlsx"
    path.write_bytes(b"stable")

    checked = FileIntegrityGuard().read_checked(path, 3, lambda source: source.read_bytes())

    assert checked.value == b"stable"
    assert checked.identity.source_file == path
    assert checked.identity.input_order == 3
    assert len(checked.identity.fingerprint) == 64


def test_input_changed_during_read_is_failed(tmp_path):
    path = tmp_path / "input.xlsx"
    path.write_bytes(b"before")

    def modify_during_read(source):
        source.write_bytes(b"after")
        return "parsed"

    with pytest.raises(SourceFileChangedError) as error:
        FileIntegrityGuard().read_checked(path, 0, modify_during_read)

    assert error.value.expected_fingerprint != error.value.actual_fingerprint
    assert error.value.source_file == path


def test_integrity_failure_overrides_reader_error_and_preserves_cause(tmp_path):
    path = tmp_path / "input.xlsx"
    path.write_bytes(b"before")

    def fail_after_modifying(source):
        source.write_bytes(b"changed")
        raise ValueError("parser failed")

    with pytest.raises(SourceFileChangedError) as error:
        FileIntegrityGuard().read_checked(path, 0, fail_after_modifying)

    assert isinstance(error.value.__cause__, ValueError)


def test_reader_error_is_preserved_when_input_is_unchanged(tmp_path):
    path = tmp_path / "input.xlsx"
    path.write_bytes(b"stable")

    def fail_without_modifying(source):
        raise LookupError("parser failed")

    with pytest.raises(LookupError, match="parser failed"):
        FileIntegrityGuard().read_checked(path, 0, fail_without_modifying)


def test_integrity_guard_never_modifies_the_input(tmp_path):
    path = tmp_path / "input.xlsx"
    original = b"read only source"
    path.write_bytes(original)

    FileIntegrityGuard().read_checked(path, 0, lambda source: source.read_bytes())

    assert path.read_bytes() == original
