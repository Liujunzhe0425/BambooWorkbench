import locale
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QProcess


@dataclass(frozen=True)
class ProcessCleanupResult:
    process_stopped: bool
    tree_terminated: bool
    detail: str


@dataclass(frozen=True)
class TaskkillAttempt:
    succeeded: bool
    detail: str


def terminate_process_tree(
    process: QProcess, grace_ms: int = 500, force_ms: int = 2_000
) -> ProcessCleanupResult:
    if process.state() == QProcess.ProcessState.NotRunning:
        return ProcessCleanupResult(True, False, "process was already stopped; tree unconfirmed")

    if sys.platform == "win32":
        return _terminate_windows_tree(process, grace_ms, force_ms)

    process.terminate()
    if not process.waitForFinished(grace_ms):
        process.kill()
        process.waitForFinished(force_ms)
    stopped = process.state() == QProcess.ProcessState.NotRunning
    detail = "direct process stopped; process-tree termination is unavailable"
    if not stopped:
        detail = "direct process cleanup failed; process tree unconfirmed"
    return ProcessCleanupResult(stopped, False, detail)


def _terminate_windows_tree(
    process: QProcess, grace_ms: int, force_ms: int
) -> ProcessCleanupResult:
    process_id = int(process.processId())
    graceful = _run_taskkill(process_id, force=False, timeout_ms=grace_ms)
    if graceful.succeeded:
        process.waitForFinished(grace_ms)
        if process.state() == QProcess.ProcessState.NotRunning:
            return ProcessCleanupResult(True, True, graceful.detail)

    forced = _run_taskkill(process_id, force=True, timeout_ms=force_ms)
    if forced.succeeded:
        process.waitForFinished(force_ms)
        if process.state() == QProcess.ProcessState.NotRunning:
            return ProcessCleanupResult(True, True, forced.detail)

    if process.state() != QProcess.ProcessState.NotRunning:
        process.kill()
        process.waitForFinished(force_ms)
    stopped = process.state() == QProcess.ProcessState.NotRunning
    direct_detail = "direct process stopped" if stopped else "direct process cleanup failed"
    return ProcessCleanupResult(
        stopped,
        False,
        f"{graceful.detail}; {forced.detail}; {direct_detail}; process tree unconfirmed",
    )


def _run_taskkill(process_id: int, *, force: bool, timeout_ms: int) -> TaskkillAttempt:
    attempt = "forced" if force else "graceful"
    system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    command = [str(system_root / "System32" / "taskkill.exe"), "/PID", str(process_id), "/T"]
    if force:
        command.append("/F")
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=max(timeout_ms, 1) / 1_000,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return TaskkillAttempt(False, f"{attempt} taskkill timed out after {timeout_ms} ms")
    except OSError as exc:
        return TaskkillAttempt(False, f"{attempt} taskkill failed to start: {type(exc).__name__}")
    if completed.returncode == 0:
        return TaskkillAttempt(True, f"{attempt} taskkill succeeded")
    output = (completed.stderr or completed.stdout).decode(
        locale.getencoding(), errors="replace"
    ).strip()
    detail = f"{attempt} taskkill exited with code {completed.returncode}"
    return TaskkillAttempt(False, f"{detail}: {output}" if output else detail)
