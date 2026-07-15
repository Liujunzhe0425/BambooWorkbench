import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"
LAUNCHER = MODULE_ROOT / "run_module.bat"


def run_cli(*arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHER), *arguments],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def valid_job(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    input_file = tmp_path / "input.xlsx"
    input_file.write_bytes(b"bootstrap input")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "t03-exit-001",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
    }
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(payload), encoding="utf-8")
    return job_path, output_dir, payload


def test_invalid_cli_returns_2() -> None:
    for arguments in (("run",), ("run", "--job", "relative.json"), ("unknown",)):
        completed = run_cli(*arguments)
        assert completed.returncode == 2
        assert completed.stdout == ""
        assert completed.stderr


@pytest.mark.parametrize(
    ("replacement", "diagnostic"),
    [
        ({"schema_version": "2.0"}, "schema_version"),
        ({"module_id": "boiling"}, "module_id"),
        ({"job_id": "bad"}, "job_id"),
        ({"output_dir": "relative/output"}, "output_dir"),
        ({"extra": "forbidden"}, "extra"),
        ({"phase": "finalize", "parent_job_id": None}, "parent_job_id"),
    ],
)
def test_invalid_job_returns_2_without_stdout_or_result(
    tmp_path: Path, replacement: dict[str, object], diagnostic: str
) -> None:
    job_path, output_dir, payload = valid_job(tmp_path)
    payload.update(replacement)
    job_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = run_cli("run", "--job", str(job_path.resolve()))

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert diagnostic in completed.stderr
    assert not (output_dir / "result.json").exists()


def test_malformed_job_returns_2_without_traceback(tmp_path: Path) -> None:
    job_path = tmp_path / "job.json"
    job_path.write_text("{not json", encoding="utf-8")

    completed = run_cli("run", "--job", str(job_path.resolve()))

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "job" in completed.stderr.lower()
    assert "traceback" not in completed.stderr.lower()


def test_result_write_failure_returns_3(tmp_path: Path) -> None:
    job_path, output_dir, _ = valid_job(tmp_path)
    (output_dir / "result.json").mkdir()

    completed = run_cli("run", "--job", str(job_path.resolve()))

    assert completed.returncode == 3
    assert completed.stderr
    assert "traceback" not in completed.stderr.lower()
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [event["percent"] for event in events] == [0]
    assert (output_dir / "result.json").is_dir()
    assert not list(output_dir.glob("*.tmp"))


def test_non_xlsx_input_returns_2_before_progress_or_output(tmp_path: Path) -> None:
    job_path, output_dir, payload = valid_job(tmp_path)
    input_file = tmp_path / "input.txt"
    input_file.write_bytes(b"not an xlsx workbook")
    payload["input_files"] = [str(input_file.resolve())]
    job_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = run_cli("run", "--job", str(job_path.resolve()))

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr
    assert not (output_dir / "result.json").exists()


def test_result_target_cannot_overwrite_job_file(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    input_file = input_dir / "input.xlsx"
    input_file.write_bytes(b"bootstrap input")
    payload = {
        "schema_version": "1.0",
        "job_id": "t03-path-001",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(tmp_path.resolve()),
    }
    job_path = tmp_path / "result.json"
    original_bytes = json.dumps(payload).encode("utf-8")
    job_path.write_bytes(original_bytes)
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()

    completed = run_cli("run", "--job", str(job_path.resolve()))

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr
    assert job_path.read_bytes() == original_bytes
    assert hashlib.sha256(job_path.read_bytes()).hexdigest() == original_sha256


def test_output_dir_cannot_equal_input_parent(tmp_path: Path) -> None:
    job_dir = tmp_path / "jobs"
    job_dir.mkdir()
    input_file = tmp_path / "input.xlsx"
    input_file.write_bytes(b"bootstrap input")
    payload = {
        "schema_version": "1.0",
        "job_id": "t03-path-002",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(tmp_path.resolve()),
    }
    job_path = job_dir / "job.json"
    job_path.write_text(json.dumps(payload), encoding="utf-8")

    completed = run_cli("run", "--job", str(job_path.resolve()))

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr
    assert not (tmp_path / "result.json").exists()
