import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess


def terminate_process_tree(process: QProcess, grace_ms: int = 500) -> None:
    if process.state() == QProcess.ProcessState.NotRunning:
        return

    if sys.platform == "win32":
        _terminate_windows_tree(process, grace_ms)
        return

    process.terminate()
    if not process.waitForFinished(grace_ms):
        process.kill()
        process.waitForFinished(grace_ms)


def _terminate_windows_tree(process: QProcess, grace_ms: int) -> None:
    process_id = int(process.processId())
    terminated = _run_taskkill(process_id, force=False, timeout_ms=grace_ms)
    if not terminated or not process.waitForFinished(grace_ms):
        _run_taskkill(process_id, force=True, timeout_ms=grace_ms)
        process.waitForFinished(grace_ms)
    if process.state() != QProcess.ProcessState.NotRunning:
        process.kill()
        process.waitForFinished(grace_ms)


def _run_taskkill(process_id: int, *, force: bool, timeout_ms: int) -> bool:
    system_root = Path(os.environ.get("SYSTEMROOT", r"C:\Windows"))
    command = [str(system_root / "System32" / "taskkill.exe"), "/PID", str(process_id), "/T"]
    if force:
        command.append("/F")
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=max(timeout_ms, 1) / 1_000,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0
