import json
import subprocess
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"
LAUNCHER = MODULE_ROOT / "run_module.bat"
RESULT_SCHEMA = ROOT / "contracts" / "schemas" / "module-result.schema.json"


def write_job(tmp_path: Path, **overrides: object) -> tuple[Path, Path, dict[str, object]]:
    input_file = tmp_path / "input.xlsx"
    input_file.write_bytes(b"bootstrap input")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "t03-job-001",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    payload.update(overrides)
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(payload), encoding="utf-8")
    return job_path, output_dir, payload


def run_job(job_path: Path, *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(LAUNCHER), "run", "--job", str(job_path.resolve())],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_minimal_draft_writes_schema_valid_result_last(tmp_path: Path) -> None:
    job_path, output_dir, job = write_job(tmp_path)

    completed = run_job(job_path)

    assert completed.returncode == 0
    assert completed.stderr == ""
    progress = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [event["percent"] for event in progress] == [0, 100]
    result_path = output_dir / "result.json"
    assert result_path.is_file()
    result = json.loads(result_path.read_text(encoding="utf-8"))
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(result, schema, format_checker=jsonschema.FormatChecker())
    assert result["job_id"] == job["job_id"]
    assert result["module_id"] == "moisture"
    assert result["module_version"] == "1.0.1"
    assert result["status"] == "failed"
    assert result["outputs"] == []
    assert result["summary"] == {
        "input_count": 1,
        "processed_count": 0,
        "skipped_count": 0,
        "failed_count": 1,
        "anomaly_count": 0,
        "confirmation_count": 0,
    }
    assert result["file_results"][0]["extracted_records"] == 0
    assert "not implemented" not in result["analysis_summary"].lower()
    assert result["analysis_summary"] == "已处理 0 个工作簿，跳过 0 个，失败 1 个。"


def test_valid_finalize_identity_boundary_writes_current_job_result(tmp_path: Path) -> None:
    confirmation_file = tmp_path / "confirmation.json"
    confirmation_file.write_text("{}", encoding="utf-8")
    job_path, output_dir, _ = write_job(
        tmp_path,
        job_id="t03-finalize-001",
        phase="finalize",
        parent_job_id="t03-parent-001",
        confirmation_file=str(confirmation_file.resolve()),
    )

    completed = run_job(job_path)

    assert completed.returncode == 0
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["job_id"] == "t03-finalize-001"
    assert result["status"] == "failed"
    assert result["outputs"] == []


def test_atomic_json_uses_same_directory_temporary_file_and_replace(
    tmp_path: Path, monkeypatch
) -> None:
    import sys

    sys.path.insert(0, str(MODULE_ROOT / "src"))
    try:
        from moisture.infrastructure import atomic_write
    finally:
        sys.path.pop(0)

    destination = tmp_path / "output" / "result.json"
    destination.parent.mkdir()
    calls: list[tuple[Path, Path]] = []
    original_replace = atomic_write.os.replace

    def replace(source: str | Path, target: str | Path) -> None:
        calls.append((Path(source), Path(target)))
        original_replace(source, target)

    monkeypatch.setattr(atomic_write.os, "replace", replace)

    payload = {
        "schema_version": "1.0",
        "job_id": "atomic-write-job",
        "module_id": "moisture",
        "module_version": "0.1.0",
        "status": "success",
        "summary": {
            "input_count": 0,
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 0,
            "confirmation_count": 0,
        },
        "started_at": "2026-07-16T08:00:00+00:00",
        "finished_at": "2026-07-16T08:00:00+00:00",
    }

    atomic_write.write_json_atomic(destination, payload)

    written = json.loads(destination.read_text(encoding="utf-8"))
    assert written["job_id"] == payload["job_id"]
    assert written["status"] == payload["status"]
    assert len(calls) == 1
    temporary, target = calls[0]
    assert temporary.parent == destination.parent
    assert target == destination
    assert temporary != destination
    assert not temporary.exists()
