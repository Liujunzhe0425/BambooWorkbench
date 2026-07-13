import locale
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QProcess, QProcessEnvironment

if TYPE_CHECKING:
    from .registry import RegisteredModule


def run_healthcheck(
    module: "RegisteredModule", timeout_ms: int = 10_000
) -> tuple[bool, str]:
    process = QProcess()
    process.setWorkingDirectory(str(module.path))
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    process.setProcessEnvironment(_process_environment(module))

    launcher = module.path / module.manifest.entrypoint
    command = subprocess.list2cmdline([str(launcher), "self-check"])
    process.setProgram(os.environ.get("COMSPEC") or "cmd.exe")
    process.setNativeArguments(f'/d /s /c "{command}"')

    started_at = time.monotonic()
    process.start()
    if not process.waitForStarted(max(timeout_ms, 0)):
        return False, f"failed to start health check: {process.errorString()}"

    elapsed_ms = int((time.monotonic() - started_at) * 1_000)
    remaining_ms = max(timeout_ms - elapsed_ms, 0)
    if not process.waitForFinished(remaining_ms):
        process.kill()
        process.waitForFinished(1_000)
        return False, f"health check timed out after {timeout_ms} ms"

    output = bytes(process.readAll()).decode(locale.getencoding(), errors="replace").strip()
    exit_code = process.exitCode()
    if process.exitStatus() != QProcess.ExitStatus.NormalExit or exit_code != 0:
        detail = f"health check exited with code {exit_code}"
        return False, f"{detail}: {output}" if output else detail
    return True, output or "ok"


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
    package_root = str(module.path.parent.parent)
    inherited_pythonpath = environment.value("PYTHONPATH")
    environment.insert(
        "PYTHONPATH",
        os.pathsep.join((package_root, inherited_pythonpath))
        if inherited_pythonpath
        else package_root,
    )
    return environment
