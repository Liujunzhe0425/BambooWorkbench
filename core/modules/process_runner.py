import sys
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult
from core.platform.path_safety import resolve_path

from .progress_parser import parse_progress
from .registry import RegisteredModule


def _resolve_path(path: Path, *, strict: bool = False) -> Path:
    return resolve_path(path, "filesystem", strict=strict)


def resolve_contained_file(path: Path, root: Path, label: str) -> Path:
    resolved_root = _resolve_path(root, strict=True)
    try:
        resolved_path = _resolve_path(path, strict=True)
    except FileNotFoundError as exc:
        raise ValueError(f"{label} is not a file") from exc
    if not resolved_path.is_relative_to(resolved_root):
        raise ValueError(f"{label} is outside output_dir")
    if not resolved_path.is_file():
        raise ValueError(f"{label} is not a file")
    return resolved_path


class ModuleProcessRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        timeout_ms: int = 120_000,
        cancellation_grace_ms: int = 500,
        process_factory: Callable[[QObject], QProcess] = QProcess,
    ) -> None:
        super().__init__()
        self.timeout_ms = timeout_ms
        self.cancellation_grace_ms = cancellation_grace_ms
        self._process_factory = process_factory
        self._process: QProcess | None = None
        self._job: JobRequest | None = None
        self._module: RegisteredModule | None = None
        self._stdout_buffer = bytearray()
        self._generation = 0
        self._active_generation: int | None = None
        self._pending_terminal: tuple[str, object | None] | None = None

    @property
    def is_running(self) -> bool:
        return self._active_generation is not None

    def start(self, module: RegisteredModule, job_path: Path) -> None:
        if self.is_running:
            raise RuntimeError("module process run is already active")

        try:
            resolved_job_path = _resolve_path(job_path, strict=True)
            job = JobRequest.model_validate_json(resolved_job_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError, ValueError) as exc:
            self.failed.emit(f"invalid job request: {exc}")
            return
        if job.module_id != module.manifest.module_id:
            self.failed.emit("job module_id does not match registered module")
            return

        try:
            entrypoint = _resolve_path(module.path / module.manifest.entrypoint)
            host = _resolve_path(Path(__file__).with_name("process_host.py"))
        except (OSError, ValueError) as exc:
            self.failed.emit(str(exc))
            return

        self._generation += 1
        generation = self._generation
        process = self._process_factory(self)
        self._process = process
        self._job = job
        self._module = module
        self._stdout_buffer.clear()
        self._pending_terminal = None
        self._active_generation = generation
        process.readyReadStandardOutput.connect(lambda: self._read_stdout(generation, process))
        process.finished.connect(
            lambda exit_code, status: self._finished(generation, process, exit_code, status)
        )
        process.errorOccurred.connect(lambda error: self._process_error(generation, process, error))

        environment = QProcessEnvironment.systemEnvironment()
        runtime_dir = str(Path(sys.executable).parent)
        environment.insert("PATH", f"{runtime_dir};{environment.value('PATH')}")
        environment.insert("PYTHONPATH", str(Path(__file__).parents[2]))
        environment.insert("PYTHONUTF8", "1")
        process.setProcessEnvironment(environment)
        process.setWorkingDirectory(str(module.path))
        process.start(
            sys.executable,
            [
                str(host),
                "--launcher",
                str(entrypoint),
                "run",
                "--job",
                str(resolved_job_path),
            ],
        )
        QTimer.singleShot(
            self.timeout_ms,
            lambda: self._timeout(generation, process),
        )

    def cancel(self) -> bool:
        if (
            not self.is_running
            or self._pending_terminal is not None
            or self._process is None
            or self._process.state() == QProcess.ProcessState.NotRunning
        ):
            return False
        assert self._active_generation is not None
        return self._request_stop(
            self._active_generation,
            self._process,
            "cancelled",
            None,
        )

    def _read_stdout(self, generation: int, process: QProcess) -> None:
        data = bytes(process.readAllStandardOutput())
        if not self._is_current(generation, process):
            return
        self._stdout_buffer.extend(data)
        if self._pending_terminal is not None:
            return
        while (newline := self._stdout_buffer.find(b"\n")) >= 0:
            line = bytes(self._stdout_buffer[: newline + 1])
            del self._stdout_buffer[: newline + 1]
            try:
                event = parse_progress(line)
            except (UnicodeError, ValidationError, ValueError) as exc:
                self._request_stop(
                    generation,
                    process,
                    "failed",
                    f"invalid progress event: {exc}",
                )
                return
            self.progress.emit(event)

    def _finished(
        self,
        generation: int,
        process: QProcess,
        exit_code: int,
        _status: QProcess.ExitStatus,
    ) -> None:
        if not self._is_current(generation, process):
            return
        self._read_stdout(generation, process)
        if self._pending_terminal is not None:
            self._emit_pending_terminal(generation, process)
            return
        if self._stdout_buffer:
            self._finalize(
                generation,
                process,
                "failed",
                "unterminated progress event at end of stdout",
            )
            return
        if exit_code != 0:
            error_text = (
                bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
            )
            detail = f"module exited with code {exit_code}"
            self._finalize(
                generation,
                process,
                "failed",
                f"{detail}: {error_text}" if error_text else detail,
            )
            return
        try:
            result = self._load_and_validate_result()
        except Exception as exc:
            self._finalize(generation, process, "failed", str(exc))
            return
        self._finalize(generation, process, "completed", result)

    def _load_and_validate_result(self) -> ModuleResult:
        if self._job is None or self._module is None:
            raise ValueError("runner lost job or module identity")
        output_dir = _resolve_path(Path(self._job.output_dir), strict=True)
        candidate = output_dir / "result.json"
        if not candidate.is_file():
            raise ValueError("result.json is missing")
        result_path = resolve_contained_file(candidate, output_dir, "result.json")
        try:
            result = ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        except (UnicodeError, ValidationError) as exc:
            raise ValueError(f"invalid result.json: {exc}") from exc
        if result.job_id != self._job.job_id:
            raise ValueError("result job_id does not match job request")
        if result.module_id != self._module.manifest.module_id:
            raise ValueError("result module_id does not match registered module")

        for output in result.outputs:
            resolve_contained_file(Path(output.path), output_dir, "output artifact")

        input_files = {_resolve_path(Path(path)) for path in self._job.input_files}
        for file_result in result.file_results:
            if _resolve_path(Path(file_result.source_file)) not in input_files:
                raise ValueError("file result source is not a job input")
        return result

    def _timeout(self, generation: int, process: QProcess) -> None:
        if not self._is_current(generation, process) or self._pending_terminal is not None:
            return
        self._request_stop(generation, process, "failed", "module timed out")

    def _process_error(
        self, generation: int, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if not self._is_current(generation, process):
            return
        if self._pending_terminal is None:
            self._pending_terminal = (
                "failed",
                f"module process error: {error.name}",
            )
        if process.state() == QProcess.ProcessState.NotRunning:
            QTimer.singleShot(
                0,
                lambda: self._emit_pending_if_stopped(generation, process),
            )
        else:
            self._stop_process(generation, process)

    def _request_stop(
        self,
        generation: int,
        process: QProcess,
        kind: str,
        payload: object | None,
    ) -> bool:
        if not self._is_current(generation, process) or self._pending_terminal is not None:
            return False
        self._pending_terminal = (kind, payload)
        if process.state() == QProcess.ProcessState.NotRunning:
            QTimer.singleShot(
                0,
                lambda: self._emit_pending_if_stopped(generation, process),
            )
            return True
        self._stop_process(generation, process)
        return True

    def _stop_process(self, generation: int, process: QProcess) -> None:
        process.terminate()
        QTimer.singleShot(
            self.cancellation_grace_ms,
            lambda: self._force_kill(generation, process),
        )

    def _force_kill(self, generation: int, process: QProcess) -> None:
        if self._is_current(generation, process) and (
            process.state() != QProcess.ProcessState.NotRunning
        ):
            process.kill()

    def _emit_pending_if_stopped(self, generation: int, process: QProcess) -> None:
        if self._is_current(generation, process) and (
            process.state() == QProcess.ProcessState.NotRunning
        ):
            self._emit_pending_terminal(generation, process)

    def _emit_pending_terminal(self, generation: int, process: QProcess) -> None:
        if self._pending_terminal is None:
            return
        kind, payload = self._pending_terminal
        self._finalize(generation, process, kind, payload)

    def _finalize(
        self,
        generation: int,
        process: QProcess,
        kind: str,
        payload: object | None,
    ) -> None:
        if not self._is_current(generation, process):
            return
        self._active_generation = None
        self._pending_terminal = None
        self._process = None
        self._job = None
        self._module = None
        process.deleteLater()
        if kind == "completed":
            self.completed.emit(payload)
        elif kind == "failed":
            self.failed.emit(str(payload))
        else:
            self.cancelled.emit()

    def _is_current(self, generation: int, process: QProcess) -> bool:
        return self._active_generation == generation and self._process is process
