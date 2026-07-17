from __future__ import annotations

import hashlib
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.domain.models import InputFileIdentity  # noqa: E402
from moisture.infrastructure.hashing import sha256_file  # noqa: E402


def test_sha256_file_hashes_content_in_streaming_chunks(tmp_path, monkeypatch):
    path = tmp_path / "large.xlsx"
    content = b"a" * (2 * 1024 * 1024 + 17)
    path.write_bytes(content)

    read_sizes: list[int] = []
    real_open = type(path).open

    class TrackedReader:
        def __init__(self, reader):
            self._reader = reader

        def __enter__(self):
            self._reader.__enter__()
            return self

        def __exit__(self, *args):
            return self._reader.__exit__(*args)

        def read(self, size=-1):
            read_sizes.append(size)
            return self._reader.read(size)

    def tracked_open(self, *args, **kwargs):
        return TrackedReader(real_open(self, *args, **kwargs))

    monkeypatch.setattr(type(path), "open", tracked_open)

    assert sha256_file(path) == hashlib.sha256(content).hexdigest()
    assert read_sizes
    assert -1 not in read_sizes
    assert max(read_sizes) <= 1024 * 1024


def test_identity_does_not_depend_on_absolute_path(tmp_path):
    first = tmp_path / "first" / "input.xlsx"
    second = tmp_path / "second" / "renamed.xlsx"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"same workbook bytes")
    second.write_bytes(b"same workbook bytes")

    first_identity = InputFileIdentity(first, sha256_file(first), 0)
    second_identity = InputFileIdentity(second, sha256_file(second), 1)

    assert first_identity.fingerprint == second_identity.fingerprint


def test_content_change_changes_fingerprint(tmp_path):
    path = tmp_path / "input.xlsx"
    path.write_bytes(b"before")
    before = sha256_file(path)

    path.write_bytes(b"after")

    assert sha256_file(path) != before
