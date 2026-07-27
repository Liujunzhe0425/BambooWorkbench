import json
import sys
from collections.abc import Callable
from pathlib import Path

from jsonschema import Draft202012Validator
from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from core.contracts.enums import TaskStatus
from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult
from core.platform.path_safety import resolve_path

from .host_runtime import add_packaged_host_environment, module_host_command
from .process_control import terminate_process
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


def _requires_monthly_snapshot(
    job: JobRequest,
    has_monthly_contract: bool,
    result_status: TaskStatus,
) -> bool:
    return (
        job.phase.value == "finalize"
        and has_monthly_contract
        and job.period_year is not None
        and job.period_month is not None
        and result_status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}
    )


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
        self._environment_overrides: dict[str, str] = {}

    @property
    def is_running(self) -> bool:
        return self._process is not None

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
            program, arguments = module_host_command(
                [
                    "--launcher",
                    str(entrypoint),
                    "run",
                    "--job",
                    str(resolved_job_path),
                ]
            )
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
        if not getattr(sys, "frozen", False):
            environment.insert("BAMBOO_MODULE_PYTHON", str(Path(sys.executable).resolve()))
        for name, value in self._environment_overrides.items():
            environment.insert(name, value)
        add_packaged_host_environment(environment)
        process.setProcessEnvironment(environment)
        process.setWorkingDirectory(str(module.path))
        process.start(program, arguments)
        QTimer.singleShot(
            self.timeout_ms,
            lambda: self._timeout(generation, process),
        )

    def set_environment_overrides(self, values: dict[str, str]) -> None:
        if self.is_running:
            raise RuntimeError("cannot change module environment while running")
        for name, value in values.items():
            if (
                name != name.upper()
                or not name.startswith("BAMBOO_")
                or not name.replace("_", "").isalnum()
            ):
                raise ValueError("module environment name is not allowed")
            if not isinstance(value, str) or "\x00" in value:
                raise ValueError("module environment value is invalid")
        self._environment_overrides = dict(values)

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

    def shutdown(self, timeout_ms: int = 3_000) -> bool:
        """Synchronously stop the host tree without emitting a lifecycle terminal."""
        process = self._process
        if process is None:
            return True
        self._active_generation = None
        self._pending_terminal = None
        grace_ms = min(self.cancellation_grace_ms, max(timeout_ms, 0))
        force_ms = max(timeout_ms - grace_ms, 0)
        result = terminate_process(process, grace_ms=grace_ms, force_ms=force_ms)
        if not result.process_stopped:
            return False
        self._process = None
        self._job = None
        self._module = None
        self._stdout_buffer.clear()
        process.deleteLater()
        return result.process_stopped

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

        monthly_contract = self._module.manifest.monthly_rollup
        has_learning = any(prompt.learning is not None for prompt in result.confirmations)
        if has_learning and (
            monthly_contract is None or monthly_contract.learning_schema is None
        ):
            raise ValueError("module learning descriptions require a declared learning schema")
        if monthly_contract and monthly_contract.learning_schema is not None:
            learning_schema_path = resolve_contained_file(
                self._module.path / monthly_contract.learning_schema,
                self._module.path,
                "monthly learning schema",
            )
            learning_validator = Draft202012Validator(
                json.loads(learning_schema_path.read_text(encoding="utf-8"))
            )
            for prompt in result.confirmations:
                if prompt.learning is not None:
                    learning_validator.validate(prompt.learning.model_dump(mode="json"))

        snapshot = result.monthly_snapshot
        monthly_finalize = _requires_monthly_snapshot(
            self._job,
            monthly_contract is not None,
            result.status,
        )
        if monthly_finalize and snapshot is None:
            raise ValueError("monthly_rollup module finalize result is missing a snapshot")
        if snapshot is not None:
            if result.status not in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
                raise ValueError(
                    "monthly snapshot is only valid for a successful or partial-success "
                    "monthly finalize"
                )
            if self._job.phase.value != "finalize" or monthly_contract is None:
                raise ValueError("monthly snapshot is only valid for a monthly finalize")
            if self._job.period_year is None or self._job.period_month is None:
                raise ValueError("monthly snapshot requires a job period")
            if (
                snapshot.year != self._job.period_year
                or snapshot.month != self._job.period_month
            ):
                raise ValueError("monthly snapshot period does not match the job")
            snapshot_path = resolve_contained_file(
                Path(snapshot.path), output_dir, "monthly snapshot"
            )
            schema_path = resolve_contained_file(
                self._module.path / monthly_contract.snapshot_schema,
                self._module.path,
                "monthly snapshot schema",
            )
            raw_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            Draft202012Validator(
                json.loads(schema_path.read_text(encoding="utf-8"))
            ).validate(raw_snapshot)

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
