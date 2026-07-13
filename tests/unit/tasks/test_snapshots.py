import hashlib
import os
from pathlib import Path

import pytest

from core.tasks.snapshots import snapshot_inputs


def test_snapshot_inputs_copies_through_task_local_temp_then_atomically_renames(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source" / "sample.XLSX"
    source.parent.mkdir()
    original = b"source-bytes"
    source.write_bytes(original)
    task_dir = tmp_path / "task"
    replacements: list[tuple[Path, Path]] = []
    real_replace = os.replace

    def observed_replace(
        source_path: str | os.PathLike[str], target_path: str | os.PathLike[str]
    ) -> None:
        temporary = Path(source_path)
        target = Path(target_path)
        assert temporary.parent == task_dir / "inputs"
        assert temporary.is_file()
        assert not target.exists()
        replacements.append((temporary, target))
        real_replace(temporary, target)

    monkeypatch.setattr(os, "replace", observed_replace)

    snapshots = snapshot_inputs([source], task_dir, supported_extensions=[".xlsx"])

    assert len(replacements) == 1
    assert snapshots[0].source == source.resolve()
    assert snapshots[0].copy.read_bytes() == original
    assert snapshots[0].fingerprint == hashlib.sha256(original).hexdigest()
    assert source.read_bytes() == original
    assert list((task_dir / "inputs").glob(".*.tmp")) == []


@pytest.mark.parametrize(
    ("kind", "message"),
    [
        ("none", "at least one input"),
        ("missing", "regular file"),
        ("directory", "regular file"),
        ("empty", "must not be empty"),
        ("unsupported", "unsupported input extension"),
    ],
)
def test_snapshot_inputs_rejects_invalid_inputs_before_copying(
    tmp_path: Path, kind: str, message: str
) -> None:
    valid = tmp_path / "valid.xlsx"
    valid.write_bytes(b"valid")
    invalid = tmp_path / "invalid.xlsx"
    if kind == "none":
        inputs: list[Path] = []
    elif kind == "missing":
        inputs = [valid, invalid]
    elif kind == "directory":
        invalid.mkdir()
        inputs = [valid, invalid]
    elif kind == "empty":
        invalid.touch()
        inputs = [valid, invalid]
    else:
        invalid = tmp_path / "invalid.csv"
        invalid.write_bytes(b"invalid")
        inputs = [valid, invalid]

    task_dir = tmp_path / "task"
    with pytest.raises(ValueError, match=message):
        snapshot_inputs(inputs, task_dir, supported_extensions=[".xlsx"])

    assert not task_dir.exists()
    assert valid.read_bytes() == b"valid"
