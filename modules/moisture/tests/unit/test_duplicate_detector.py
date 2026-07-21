from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.infrastructure.duplicate_detector import DuplicateDetector  # noqa: E402
from moisture.infrastructure.hashing import sha256_file  # noqa: E402


def test_duplicate_content_is_processed_once(tmp_path):
    first = tmp_path / "first.xlsx"
    duplicate = tmp_path / "renamed.xlsx"
    unique = tmp_path / "unique.xlsx"
    first.write_bytes(b"same")
    duplicate.write_bytes(b"same")
    unique.write_bytes(b"different")

    decisions = DuplicateDetector().classify([first, duplicate, unique])

    assert [decision.status for decision in decisions] == ["process", "skipped", "process"]
    assert decisions[1].reason == "duplicate_content"
    assert decisions[1].canonical_input_order == 0
    assert decisions[0].identity is not None
    assert decisions[1].identity is not None
    assert decisions[0].identity.fingerprint == decisions[1].identity.fingerprint


def test_office_temporary_workbook_is_skipped_without_reading(tmp_path):
    temporary = tmp_path / "~$open.xlsx"
    ordinary = tmp_path / "ordinary.xlsx"
    temporary.write_bytes(b"temporary")
    ordinary.write_bytes(b"ordinary")
    hashed_paths = []

    def tracking_hasher(path):
        hashed_paths.append(path)
        return sha256_file(path)

    decisions = DuplicateDetector(hasher=tracking_hasher).classify([temporary, ordinary])

    assert decisions[0].status == "skipped"
    assert decisions[0].reason == "office_temporary_file"
    assert decisions[0].identity is None
    assert hashed_paths == [ordinary]


def test_decisions_preserve_declared_input_order(tmp_path):
    paths = [tmp_path / name for name in ("z.xlsx", "a.xlsx", "m.xlsx")]
    for index, path in enumerate(paths):
        path.write_bytes(str(index).encode())

    decisions = DuplicateDetector().classify(paths)

    assert [decision.source_file for decision in decisions] == paths
    assert [decision.input_order for decision in decisions] == [0, 1, 2]


def test_duplicate_decision_has_stable_info_message(tmp_path):
    first = tmp_path / "first.xlsx"
    duplicate = tmp_path / "duplicate.xlsx"
    first.write_bytes(b"same")
    duplicate.write_bytes(b"same")

    duplicate_decision = DuplicateDetector().classify([first, duplicate])[1]

    assert duplicate_decision.message == "duplicate content; canonical input order: 0"
