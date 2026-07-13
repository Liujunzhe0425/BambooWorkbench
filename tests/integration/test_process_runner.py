import json
import sys
from pathlib import Path

import pytest
import shiboken6
from PySide6.QtCore import QObject, QProcess
from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from core.contracts.progress import ProgressEvent
from core.modules.process_control import ProcessCleanupResult
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry, RegisteredModule


def _write_job(
    tmp_path: Path, name: str = "normal.xlsx", job_id: str = "runner-001"
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    input_file = tmp_path / name
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job_path = tmp_path / "job.json"
    job_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": job_id,
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
if args.mode == "fragmented-progress":
    import sys
    sys.stdout.write('{"type":"progress","percent":25,')
    sys.stdout.flush()
    time.sleep(0.05)
    sys.stdout.write('"message":"fragmented"}\\n')
    sys.stdout.flush()
    time.sleep(0.2)
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
if args.mode == "unterminated-progress":
    import sys
    sys.stdout.write("not-json")
    sys.stdout.flush()
if args.mode == "delayed-result":
    time.sleep(0.5)
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
    qtbot.wait(750)
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
        ("unterminated-progress", "unterminated progress event"),
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
    assert runner.cancel() is True
    assert terminals[2].count() == 0
    _wait_terminal(qtbot, terminals)

    assert terminals[2].count() == 1


def test_cancel_returns_false_when_no_run_can_accept_cancellation() -> None:
    runner = ModuleProcessRunner()

    assert runner.cancel() is False


def test_shutdown_is_bounded_stops_real_process_and_emits_no_terminal(
    qtbot, tmp_path: Path
) -> None:
    job_path, _ = _write_job(tmp_path, name="timeout.xlsx", job_id="shutdown-job")
    runner = ModuleProcessRunner(timeout_ms=30_000)
    terminals = _terminal_spies(runner)
    runner.start(_registered_mock(), job_path)
    qtbot.waitUntil(lambda: runner.is_running, timeout=2_000)

    assert runner.shutdown(timeout_ms=3_000) is True

    qtbot.wait(100)
    assert runner.is_running is False
    assert sum(spy.count() for spy in terminals) == 0


def test_shutdown_failure_retains_ownership_blocks_callbacks_and_can_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.contracts.job import JobRequest
    from core.modules import process_runner as process_runner_module

    job_path, _ = _write_job(tmp_path, job_id="shutdown-retry-job")
    job = JobRequest.model_validate_json(job_path.read_text(encoding="utf-8"))
    module = _registered_mock()
    runner = ModuleProcessRunner()
    process = QProcess(runner)
    runner._process = process
    runner._job = job
    runner._module = module
    runner._active_generation = 1
    results = [
        ProcessCleanupResult(False, "still running"),
        ProcessCleanupResult(True, "stopped on retry"),
    ]
    calls: list[QProcess] = []

    def terminate(candidate: QProcess, **_kwargs: object) -> ProcessCleanupResult:
        calls.append(candidate)
        return results.pop(0)

    monkeypatch.setattr(process_runner_module, "terminate_process", terminate)
    terminals = _terminal_spies(runner)

    assert runner.shutdown(timeout_ms=25) is False
    runner._finished(1, process, 0, QProcess.ExitStatus.NormalExit)

    assert runner._process is process
    assert runner._job is job
    assert runner._module is module
    assert runner.is_running is True
    assert sum(spy.count() for spy in terminals) == 0
    assert runner.shutdown(timeout_ms=25) is True
    assert calls == [process, process]
    assert runner._process is None
    assert runner._job is None
    assert runner._module is None


def test_cancel_returns_false_in_not_running_callback_window() -> None:
    runner = ModuleProcessRunner()
    process = QProcess(runner)
    runner._active_generation = 1
    runner._process = process

    assert process.state() == QProcess.ProcessState.NotRunning
    assert runner.cancel() is False
    assert runner._pending_terminal is None


def test_cancel_returns_false_without_replacing_pending_terminal() -> None:
    runner = ModuleProcessRunner()
    process = QProcess(runner)
    runner._active_generation = 1
    runner._process = process
    runner._pending_terminal = ("failed", "process already failed")

    assert runner.cancel() is False
    assert runner._pending_terminal == ("failed", "process already failed")


def test_fragmented_progress_is_buffered_until_newline(qtbot, tmp_path: Path) -> None:
    job_path, _ = _write_job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=10_000)
    progress = QSignalSpy(runner.progress)
    terminals = _terminal_spies(runner)

    runner.start(_write_test_module(tmp_path, "fragmented-progress"), job_path)
    qtbot.waitUntil(lambda: progress.count() == 1, timeout=5_000)
    assert runner.is_running
    _wait_terminal(qtbot, terminals)

    assert progress.at(0)[0].message == "fragmented"


def test_job_module_mismatch_fails_without_starting_process(qtbot, tmp_path: Path) -> None:
    job_path, _ = _write_job(tmp_path)
    payload = json.loads(job_path.read_text(encoding="utf-8"))
    payload["module_id"] = "boiling"
    job_path.write_text(json.dumps(payload), encoding="utf-8")
    runner = ModuleProcessRunner()
    terminals = _terminal_spies(runner)

    runner.start(_registered_mock(), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert "job module_id does not match" in terminals[1].at(0)[0]
    assert not runner.is_running


def test_overlapping_start_raises_without_consuming_active_terminal(qtbot, tmp_path: Path) -> None:
    job_path, _ = _write_job(tmp_path, "timeout.xlsx")
    runner = ModuleProcessRunner(timeout_ms=10_000, cancellation_grace_ms=50)
    terminals = _terminal_spies(runner)
    module = _registered_mock()

    runner.start(module, job_path)
    qtbot.waitUntil(lambda: runner.is_running, timeout=5_000)
    with pytest.raises(RuntimeError, match="already active"):
        runner.start(module, job_path)
    assert sum(spy.count() for spy in terminals) == 0
    runner.cancel()
    _wait_terminal(qtbot, terminals)

    assert terminals[2].count() == 1


def test_runner_can_be_reused_sequentially(qtbot, tmp_path: Path) -> None:
    runner = ModuleProcessRunner(timeout_ms=10_000)
    terminals = _terminal_spies(runner)
    module = _registered_mock()

    first_job, _ = _write_job(tmp_path / "first", job_id="runner-001")
    runner.start(module, first_job)
    qtbot.waitUntil(lambda: terminals[0].count() == 1, timeout=15_000)
    second_job, _ = _write_job(tmp_path / "second", job_id="runner-002")
    runner.start(module, second_job)
    qtbot.waitUntil(lambda: terminals[0].count() == 2, timeout=15_000)
    qtbot.wait(750)

    assert terminals[0].count() == 2
    assert terminals[1].count() == terminals[2].count() == 0


def test_qprocess_start_error_emits_one_failure(qtbot, tmp_path: Path, monkeypatch) -> None:
    job_path, _ = _write_job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=10_000, cancellation_grace_ms=50)
    terminals = _terminal_spies(runner)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "missing-python.exe"))

    runner.start(_registered_mock(), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert "process error" in terminals[1].at(0)[0]


def test_special_job_and_launcher_paths_are_not_expanded_or_injected(qtbot, tmp_path: Path) -> None:
    special = tmp_path / "用户 & %PATH% ^ (space) !"
    special.mkdir()
    job_path, _ = _write_job(special, job_id="runner-003")
    runner = ModuleProcessRunner(timeout_ms=10_000)
    terminals = _terminal_spies(runner)

    runner.start(_write_test_module(special, "normal"), job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[0].count() == 1


@pytest.mark.parametrize("loop_name", ["job.json", "run_module.bat"])
def test_start_normalizes_path_resolution_loops_to_one_failure(
    qtbot, tmp_path: Path, monkeypatch, loop_name: str
) -> None:
    job_path, _ = _write_job(tmp_path)
    module = _write_test_module(tmp_path, "normal")
    runner = ModuleProcessRunner()
    terminals = _terminal_spies(runner)
    original_resolve = Path.resolve

    def simulated_loop(path: Path, *args, **kwargs):
        if path.name == loop_name:
            raise RuntimeError("Symlink loop from simulated test")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulated_loop)

    runner.start(module, job_path)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert "path resolution failed" in terminals[1].at(0)[0]
    assert not runner.is_running


@pytest.mark.parametrize("loop_name", ["output", "result.json", "artifact.txt", "normal.xlsx"])
def test_result_boundary_resolution_loops_fail_once_without_callback_exception(
    qtbot, tmp_path: Path, monkeypatch, loop_name: str
) -> None:
    job_path, _ = _write_job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=10_000)
    terminals = _terminal_spies(runner)
    runner.start(_write_test_module(tmp_path, "delayed-result"), job_path)
    qtbot.waitUntil(lambda: runner.is_running, timeout=5_000)
    original_resolve = Path.resolve

    def simulated_loop(path: Path, *args, **kwargs):
        if path.name == loop_name:
            raise RuntimeError("Symlink loop from simulated test")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", simulated_loop)
    _wait_terminal(qtbot, terminals)

    assert terminals[1].count() == 1
    assert "path resolution failed" in terminals[1].at(0)[0]


def test_completed_process_is_scheduled_for_qobject_deletion(qtbot, tmp_path: Path) -> None:
    processes: list[QProcess] = []

    def process_factory(parent: QObject) -> QProcess:
        process = QProcess(parent)
        processes.append(process)
        return process

    job_path, _ = _write_job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=10_000, process_factory=process_factory)
    terminals = _terminal_spies(runner)

    runner.start(_write_test_module(tmp_path, "normal"), job_path)
    _wait_terminal(qtbot, terminals)
    qtbot.waitUntil(lambda: not shiboken6.isValid(processes[0]), timeout=5_000)

    assert not any(isinstance(child, QProcess) for child in runner.children())
