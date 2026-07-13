import json
from pathlib import Path

import pytest
from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from core.contracts.progress import ProgressEvent
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry, RegisteredModule


def _write_job(tmp_path: Path, name: str = "normal.xlsx") -> tuple[Path, Path]:
    input_file = tmp_path / name
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "runner-001",
                "module_id": "moisture",
                "phase": "draft",
                "run_mode": "single",
                "input_files": [str(input_file.resolve())],
                "output_dir": str(output_dir.resolve()),
                "module_config_file": None,
                "ai_enabled": False,
                "allowed_knowledge_scopes": ["shared", "moisture"],
            }
        ),
        encoding="utf-8",
    )
    return job_path, output_dir


def _registered_mock() -> RegisteredModule:
    registry = ModuleRegistry(Path("modules"), Path("mock_modules"), True)
    registry.scan()
    return registry.get(ModuleId.MOISTURE)


def _write_test_module(tmp_path: Path, mode: str) -> RegisteredModule:
    module = _registered_mock()
    module_dir = tmp_path / f"test-module-{mode}"
    module_dir.mkdir()
    helper = module_dir / "helper.py"
    helper.write_text(
        """
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("mode")
parser.add_argument("command")
parser.add_argument("--job", type=Path, required=True)
args = parser.parse_args()
job = json.loads(args.job.read_text(encoding="utf-8"))
output_dir = Path(job["output_dir"])
output_dir.mkdir(parents=True, exist_ok=True)
if args.mode == "invalid-progress":
    print("not json", flush=True)
    time.sleep(30)
    raise SystemExit(0)
if args.mode == "missing-result":
    raise SystemExit(0)
artifact = output_dir / "artifact.txt"
artifact.write_text("local", encoding="utf-8")
now = datetime.now(timezone.utc).isoformat()
result = {
    "schema_version": "1.0", "job_id": job["job_id"],
    "module_id": job["module_id"], "module_version": "0.1.0",
    "status": "success", "rule_version": "test",
    "summary": {"input_count": 1, "processed_count": 1, "skipped_count": 0,
                "failed_count": 0, "anomaly_count": 0, "confirmation_count": 0},
    "anomalies": [], "confirmations": [],
    "outputs": [{"type": "report", "path": str(artifact.resolve()),
                 "label": "artifact", "mime_type": "text/plain"}],
    "file_results": [{"source_file": job["input_files"][0], "fingerprint": "abc",
                      "status": "success", "extracted_records": 1,
                      "missing_fields": [], "anomaly_count": 0, "error": None}],
    "service_requests": [], "analysis_summary": None, "errors": [],
    "started_at": now, "finished_at": now,
}
if args.mode == "malformed-result":
    (output_dir / "result.json").write_text("{bad", encoding="utf-8")
    raise SystemExit(0)
if args.mode == "wrong-job":
    result["job_id"] = "another-job"
if args.mode == "wrong-module":
    result["module_id"] = "boiling"
if args.mode == "escaped-output":
    escaped = output_dir.parent / "escaped.txt"
    escaped.write_text("escaped", encoding="utf-8")
    result["outputs"][0]["path"] = str(escaped.resolve())
if args.mode == "missing-output":
    result["outputs"][0]["path"] = str((output_dir / "absent.txt").resolve())
if args.mode == "foreign-source":
    result["file_results"][0]["source_file"] = str((output_dir / "foreign.xlsx").resolve())
(output_dir / "result.json").write_text(json.dumps(result), encoding="utf-8")
""".strip(),
        encoding="utf-8",
    )
    launcher = module_dir / "run_module.bat"
    launcher.write_text(
        f"@python helper.py {mode} %*\n",
        encoding="utf-8",
    )
    return RegisteredModule(module.manifest, module_dir.resolve(), True, "healthy")


def _terminal_spies(runner: ModuleProcessRunner) -> tuple[QSignalSpy, QSignalSpy, QSignalSpy]:
    return QSignalSpy(runner.completed), QSignalSpy(runner.failed), QSignalSpy(runner.cancelled)


def _wait_terminal(qtbot, spies: tuple[QSignalSpy, ...], timeout: int = 15_000) -> None:
    qtbot.waitUntil(lambda: sum(spy.count() for spy in spies) == 1, timeout=timeout)
    qtbot.wait(100)
    assert sum(spy.count() for spy in spies) == 1


def test_runner_emits_typed_progress_and_validated_result(qtbot, tmp_path: Path) -> None:
    job_path, _ = _write_job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=10_000)
    progress = QSignalSpy(runner.progress)
    terminals = _terminal_spies(runner)

    runner.start(_registered_mock(), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[0].count() == 1
    assert terminals[0].at(0)[0].status.value == "success"
    assert progress.count() == 2
    assert all(isinstance(progress.at(index)[0], ProgressEvent) for index in range(2))


@pytest.mark.parametrize(
    ("input_name", "message"),
    [("crash.xlsx", "exited with code 3"), ("invalid.xlsx", "invalid result.json")],
)
def test_runner_reports_mock_module_failures_once(
    qtbot, tmp_path: Path, input_name: str, message: str
) -> None:
    job_path, _ = _write_job(tmp_path, input_name)
    runner = ModuleProcessRunner(timeout_ms=10_000)
    terminals = _terminal_spies(runner)

    runner.start(_registered_mock(), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert message in terminals[1].at(0)[0]


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("invalid-progress", "invalid progress event"),
        ("missing-result", "result.json is missing"),
        ("malformed-result", "invalid result.json"),
        ("wrong-job", "result job_id does not match"),
        ("wrong-module", "result module_id does not match"),
        ("escaped-output", "outside output_dir"),
        ("missing-output", "output artifact is not a file"),
        ("foreign-source", "file result source is not a job input"),
    ],
)
def test_runner_rejects_invalid_protocol_or_result_once(
    qtbot, tmp_path: Path, mode: str, message: str
) -> None:
    job_path, _ = _write_job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=10_000)
    terminals = _terminal_spies(runner)

    runner.start(_write_test_module(tmp_path, mode), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert message in terminals[1].at(0)[0]


def test_timeout_fails_once_without_blocking_event_loop(qtbot, tmp_path: Path) -> None:
    job_path, _ = _write_job(tmp_path, "timeout.xlsx")
    runner = ModuleProcessRunner(timeout_ms=100, cancellation_grace_ms=50)
    terminals = _terminal_spies(runner)

    runner.start(_registered_mock(), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert "timed out" in terminals[1].at(0)[0]


def test_user_cancellation_emits_cancelled_once_and_is_nonblocking(qtbot, tmp_path: Path) -> None:
    job_path, _ = _write_job(tmp_path, "timeout.xlsx")
    runner = ModuleProcessRunner(timeout_ms=10_000, cancellation_grace_ms=50)
    terminals = _terminal_spies(runner)

    runner.start(_registered_mock(), job_path)
    qtbot.waitUntil(lambda: runner.is_running, timeout=5_000)
    runner.cancel()
    assert terminals[2].count() == 1
    _wait_terminal(qtbot, terminals)

    assert terminals[2].count() == 1
