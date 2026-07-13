from dataclasses import dataclass

from PySide6.QtCore import QProcess


@dataclass(frozen=True)
class ProcessCleanupResult:
    process_stopped: bool
    detail: str


def terminate_process(
    process: QProcess, grace_ms: int = 500, force_ms: int = 2_000
) -> ProcessCleanupResult:
    """Stop the module host; its Windows Job Object owns descendant cleanup."""
    if process.state() == QProcess.ProcessState.NotRunning:
        return ProcessCleanupResult(True, "module host already stopped")

    process.terminate()
    if process.waitForFinished(grace_ms):
        stopped = process.state() == QProcess.ProcessState.NotRunning
        if stopped:
            return ProcessCleanupResult(True, "module host terminated")

    process.kill()
    process.waitForFinished(force_ms)
    stopped = process.state() == QProcess.ProcessState.NotRunning
    detail = "module host killed" if stopped else "module host cleanup failed"
    return ProcessCleanupResult(stopped, detail)
