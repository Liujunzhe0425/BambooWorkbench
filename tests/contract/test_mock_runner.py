import json
import subprocess
import sys
from pathlib import Path


def test_mock_runner_creates_success_result(tmp_path: Path) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job = {
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
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mock_modules.common.cli",
            "--module-id",
            "moisture",
            "run",
            "--job",
            str(job_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    progress = [json.loads(line) for line in completed.stdout.splitlines()]
    assert progress == [
        {"type": "progress", "percent": 25, "message": "读取模拟输入"},
        {"type": "progress", "percent": 100, "message": "模拟处理完成"},
    ]
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
