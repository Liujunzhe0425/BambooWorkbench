# ruff: noqa: E402, I001

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "modules" / "moisture"
LAUNCHER = MODULE_ROOT / "run_module.bat"
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.run_result import InternalMoistureRunResult, InternalOutput
from moisture.contract.mapper import map_run_result
from moisture.infrastructure.atomic_write import AtomicResultWriter
from moisture.infrastructure.paths import OutputPathError


def _result_with_output(path: Path):
    now = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)
    return map_run_result(
        InternalMoistureRunResult(
            job_id="t22-path",
            phase="draft",
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            outputs=(InternalOutput("report", path, "report", "text/plain"),),
            started_at=now,
            finished_at=now,
        )
    ).result


def test_output_artifact_escape_is_rejected_without_result(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(OutputPathError, match="escapes output_dir"):
        AtomicResultWriter(output_dir).write(_result_with_output(outside))

    assert not (output_dir / "result.json").exists()
    assert outside.read_text(encoding="utf-8") == "outside"


def test_formal_bat_runs_from_unrelated_current_directory(tmp_path: Path) -> None:
    unrelated = tmp_path / "unrelated cwd"
    unrelated.mkdir()

    completed = subprocess.run(
        [str(LAUNCHER), "version"],
        cwd=unrelated,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == "1.3.4"
    assert completed.stderr == ""


def test_stdout_contains_only_progress_json_and_no_traceback(
    tmp_path: Path,
) -> None:
    source = tmp_path / "inputs" / "corrupt.xlsx"
    source.parent.mkdir()
    source.write_bytes(b"not-an-xlsx")
    output = (tmp_path / "output").resolve()
    job = tmp_path / "jobs" / "job.json"
    job.parent.mkdir()
    job.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "t22-stdout",
                "module_id": "moisture",
                "phase": "draft",
                "run_mode": "single",
                "input_files": [str(source.resolve())],
                "output_dir": str(output),
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(LAUNCHER), "run", "--job", str(job.resolve())],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [item["percent"] for item in events] == [0, 100]
    assert "Traceback" not in completed.stdout
    assert completed.stderr == ""
