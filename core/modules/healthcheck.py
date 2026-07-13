import locale
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess, QProcessEnvironment

from .host_runtime import add_packaged_host_environment, module_host_command
from .launcher import launcher_validation_error
from .process_control import ProcessCleanupResult, terminate_process

if TYPE_CHECKING:
    from .registry import RegisteredModule


def run_healthcheck(
    module: "RegisteredModule",
    timeout_ms: int = 10_000,
    *,
    process_factory: Callable[[], QProcess] = QProcess,
    process_terminator: Callable[[QProcess], ProcessCleanupResult] = terminate_process,
) -> tuple[bool, str]:
    """Run a synchronous bootstrap/background health check; never call from the UI thread."""
    launcher = (module.path / module.manifest.entrypoint).resolve()
    validation_error = launcher_validation_error(launcher)
    if validation_error is not None:
        return False, validation_error

    process = process_factory()
    process.setWorkingDirectory(str(module.path))
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    process.setProcessEnvironment(_process_environment(module))

    try:
        program, arguments = module_host_command(
            [
            "--launcher",
            str(launcher),
            "self-check",
            ]
        )
    except OSError as exc:
        return False, f"module host unavailable: {exc}"
    process.setProgram(program)
    process.setArguments(arguments)

    started_at = time.monotonic()
    process.start()
    if not process.waitForStarted(max(timeout_ms, 0)):
        detail = f"failed to start health check: {process.errorString()}"
        if process.state() in {
            QProcess.ProcessState.Starting,
            QProcess.ProcessState.Running,
        }:
            cleanup = _cleanup(process, process_terminator)
            final_stopped = process.state() == QProcess.ProcessState.NotRunning
            if not cleanup.process_stopped or not final_stopped:
                detail = f"{detail}; cleanup failed: {cleanup.detail}"
        return False, detail

    elapsed_ms = int((time.monotonic() - started_at) * 1_000)
    remaining_ms = max(timeout_ms - elapsed_ms, 0)
    if not process.waitForFinished(remaining_ms):
        cleanup = _cleanup(process, process_terminator)
        final_stopped = process.state() == QProcess.ProcessState.NotRunning
        if not cleanup.process_stopped or not final_stopped:
            return False, (
                f"health check timed out after {timeout_ms} ms; cleanup failed: "
                f"{cleanup.detail}"
            )
        return False, f"health check timed out after {timeout_ms} ms"

    output = bytes(process.readAll()).decode(locale.getencoding(), errors="replace").strip()
    exit_code = process.exitCode()
    if exit_code != 0:
        detail = f"health check exited with code {exit_code}"
        return False, f"{detail}: {output}" if output else detail
    return True, output or "ok"


def _cleanup(
    process: QProcess,
    process_terminator: Callable[[QProcess], ProcessCleanupResult],
) -> ProcessCleanupResult:
    try:
        return process_terminator(process)
    except Exception as exc:
        return ProcessCleanupResult(
            process_stopped=process.state() == QProcess.ProcessState.NotRunning,
            detail=f"cleanup raised {type(exc).__name__}",
        )


def _process_environment(module: "RegisteredModule") -> QProcessEnvironment:
    environment = QProcessEnvironment.systemEnvironment()
    python_directory = str(Path(sys.executable).resolve().parent)
    inherited_path = environment.value("PATH")
    environment.insert(
        "PATH",
        os.pathsep.join((python_directory, inherited_path))
        if inherited_path
        else python_directory,
    )
    application_root = str(Path(__file__).resolve().parents[2])
    package_root = str(module.path.parent.parent)
    inherited_pythonpath = environment.value("PYTHONPATH")
    python_paths = [application_root, package_root]
    if inherited_pythonpath:
        python_paths.append(inherited_pythonpath)
    environment.insert(
        "PYTHONPATH",
        os.pathsep.join(python_paths),
    )
    add_packaged_host_environment(environment)
    return environment
