import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.contracts.result import ModuleResult


def make_job(input_file: Path, output_dir: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "job_id": "mock-0001",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": ["shared", "moisture"],
    }


def run_mock(job_path: Path, module_id: str = "moisture") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mock_modules.common.cli",
            "--module-id",
            module_id,
            "run",
            "--job",
            str(job_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_mock_runner_creates_success_result(tmp_path: Path) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(make_job(input_file, output_dir)), encoding="utf-8")
    completed = run_mock(job_path)
    assert completed.returncode == 0
    progress = [json.loads(line) for line in completed.stdout.splitlines()]
    assert progress == [
        {"type": "progress", "percent": 25, "message": "读取模拟输入"},
        {"type": "progress", "percent": 100, "message": "模拟处理完成"},
    ]
    result = ModuleResult.model_validate_json(
        (output_dir / "result.json").read_text(encoding="utf-8")
    )
    assert result.status.value == "success"
    for artifact in result.outputs:
        artifact_path = Path(artifact.path)
        assert artifact_path.is_relative_to(output_dir)
        assert artifact_path.is_file()


def test_mock_runner_rejects_module_id_mismatch_before_output(tmp_path: Path) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(make_job(input_file, output_dir)), encoding="utf-8")

    completed = run_mock(job_path, module_id="boiling")

    assert completed.returncode == 2
    assert not output_dir.exists()
    assert "module-id mismatch" in completed.stderr.lower()
    assert "traceback" not in completed.stderr.lower()


@pytest.mark.parametrize("invalid_job", ["missing", "malformed", "contract-invalid"])
def test_mock_runner_reports_invalid_job_without_traceback(
    tmp_path: Path, invalid_job: str
) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job_path = tmp_path / "job.json"
    if invalid_job == "malformed":
        job_path.write_text("{invalid", encoding="utf-8")
    elif invalid_job == "contract-invalid":
        job = make_job(input_file, output_dir)
        job["job_id"] = "x"
        job_path.write_text(json.dumps(job), encoding="utf-8")

    completed = run_mock(job_path)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "invalid job request" in completed.stderr.lower()
    assert "traceback" not in completed.stderr.lower()


def test_mock_runner_does_not_report_completion_when_result_write_fails(tmp_path: Path) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    (output_dir / "result.json").mkdir(parents=True)
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(make_job(input_file, output_dir)), encoding="utf-8")

    completed = run_mock(job_path)

    assert completed.returncode == 3
    assert completed.stderr == "mock runtime failed\n"
    assert "traceback" not in completed.stderr.lower()
    progress = [json.loads(line) for line in completed.stdout.splitlines()]
    assert progress == [
        {"type": "progress", "percent": 25, "message": "读取模拟输入"},
    ]
