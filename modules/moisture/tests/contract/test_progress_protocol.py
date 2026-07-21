import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"
LAUNCHER = MODULE_ROOT / "run_module.bat"


def test_progress_stdout_is_json_lines_only(tmp_path: Path) -> None:
    input_file = tmp_path / "input.xlsx"
    input_file.write_bytes(b"bootstrap input")
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "t03-progress-001",
                "module_id": "moisture",
                "phase": "draft",
                "run_mode": "single",
                "input_files": [str(input_file.resolve())],
                "output_dir": str(output_dir.resolve()),
            }
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [str(LAUNCHER), "run", "--job", str(job_path.resolve())],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert completed.returncode == 0
    assert completed.stderr == ""
    lines = completed.stdout.splitlines()
    assert len(lines) == 2
    events = [json.loads(line) for line in lines]
    assert [event["percent"] for event in events] == [0, 100]
    for event in events:
        assert set(event) == {"type", "percent", "message"}
        assert event["type"] == "progress"
        assert isinstance(event["percent"], int)
        assert 0 <= event["percent"] <= 100
        assert isinstance(event["message"], str)
        assert 1 <= len(event["message"]) <= 300
