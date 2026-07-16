# ruff: noqa: E402, I001

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.run_result import InternalMoistureRunResult, InternalOutput
from moisture.contract.mapper import map_run_result
from moisture.contract.validators import ContractValidationError
from moisture.infrastructure.atomic_write import AtomicResultWriter, write_json_atomic
from moisture.infrastructure.paths import OutputPathError


def mapped_result(output: Path):
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    return map_run_result(
        InternalMoistureRunResult(
            job_id="job-1",
            phase="draft",
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            started_at=now,
            finished_at=now,
            outputs=(
                InternalOutput(
                    type="report",
                    path=output,
                    label="Report",
                    mime_type="text/markdown",
                ),
            ),
        )
    ).result


def test_result_rejects_output_outside_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(OutputPathError):
        AtomicResultWriter(output_dir).write(mapped_result(outside))

    assert not (output_dir / "result.json").exists()


def test_result_is_written_after_outputs(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output = output_dir / "analysis_report.md"
    output.write_text("complete", encoding="utf-8")
    events: list[str] = []

    import moisture.infrastructure.atomic_write as atomic_write

    original_replace = atomic_write.os.replace

    def replace(source: str | Path, destination: str | Path) -> None:
        assert output.is_file()
        events.append(Path(destination).name)
        original_replace(source, destination)

    monkeypatch.setattr(atomic_write.os, "replace", replace)

    result_path = AtomicResultWriter(output_dir).write(mapped_result(output))

    assert events == ["result.json"]
    assert result_path == output_dir / "result.json"
    assert json.loads(result_path.read_text(encoding="utf-8"))["outputs"][0][
        "path"
    ] == str(output)


def test_missing_output_is_not_referenced_by_result(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    missing = output_dir / "missing.md"

    with pytest.raises(OutputPathError):
        AtomicResultWriter(output_dir).write(mapped_result(missing))

    assert not (output_dir / "result.json").exists()


def test_existing_result_cannot_be_registered_as_business_output(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    old_result = output_dir / "result.json"
    old_result.write_text("old", encoding="utf-8")

    with pytest.raises(OutputPathError, match="business artifact"):
        AtomicResultWriter(output_dir).write(mapped_result(old_result))

    assert old_result.read_text(encoding="utf-8") == "old"


def test_atomic_failure_leaves_no_result_or_temporary_file(
    tmp_path: Path, monkeypatch
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    output = output_dir / "analysis_report.md"
    output.write_text("complete", encoding="utf-8")

    import moisture.infrastructure.atomic_write as atomic_write

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(atomic_write.os, "replace", fail_replace)

    with pytest.raises(OSError):
        AtomicResultWriter(output_dir).write(mapped_result(output))

    assert not (output_dir / "result.json").exists()
    assert not list(output_dir.glob("*.tmp"))


def test_result_named_destination_always_uses_guarded_writer(tmp_path: Path) -> None:
    destination = tmp_path / "result.json"
    destination.write_text("old", encoding="utf-8")

    with pytest.raises(ContractValidationError):
        write_json_atomic(destination, {"schema_version": "1.0"})

    assert destination.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.tmp"))
