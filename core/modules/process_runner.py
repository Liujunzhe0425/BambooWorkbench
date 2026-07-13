import sys
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult

from .progress_parser import parse_progress
from .registry import RegisteredModule


class ModuleProcessRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self, timeout_ms: int = 120_000, cancellation_grace_ms: int = 500
    ) -> None:
        super().__init__()
        self.timeout_ms = timeout_ms
        self.cancellation_grace_ms = cancellation_grace_ms
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._force_kill)
        self._job: JobRequest | None = None
        self._module: RegisteredModule | None = None
        self._terminal_emitted = False

    @property
    def is_running(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start(self, module: RegisteredModule, job_path: Path) -> None:
        if self.is_running:
            self._emit_failed("module process is already running")
            return
        self._terminal_emitted = False
        self._job = None
        self._module = module
        try:
            resolved_job_path = job_path.resolve(strict=True)
            self._job = JobRequest.model_validate_json(
                resolved_job_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, ValidationError) as exc:
            self._emit_failed(f"invalid job request: {exc}")
            return
        if self._job.module_id != module.manifest.module_id:
            self._emit_failed("job module_id does not match registered module")
            return

        entrypoint = (module.path / module.manifest.entrypoint).resolve()
        host = Path(__file__).with_name("process_host.py").resolve()
        environment = QProcessEnvironment.systemEnvironment()
        runtime_dir = str(Path(sys.executable).parent)
        environment.insert("PATH", f"{runtime_dir};{environment.value('PATH')}")
        environment.insert("PYTHONPATH", str(Path(__file__).parents[2]))
        environment.insert("PYTHONUTF8", "1")
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(str(module.path))
        self.process.start(
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
        self.timer.start(self.timeout_ms)

    def cancel(self) -> None:
        if self._terminal_emitted or not self.is_running:
            return
        self._terminal_emitted = True
        self.timer.stop()
        self.cancelled.emit()
        self._stop_process()

    def _read_stdout(self) -> None:
        if self._terminal_emitted:
            self.process.readAllStandardOutput()
            return
        while self.process.canReadLine():
            line = bytes(self.process.readLine())
            try:
                event = parse_progress(line)
            except (UnicodeError, ValidationError, ValueError) as exc:
                self._emit_failed(f"invalid progress event: {exc}")
                self._stop_process()
                return
            self.progress.emit(event)

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.timer.stop()
        self._kill_timer.stop()
        if self._terminal_emitted:
            return
        self._read_stdout()
        if self._terminal_emitted:
            return
        if exit_code != 0:
            error_text = bytes(self.process.readAllStandardError()).decode(
                "utf-8", errors="replace"
            ).strip()
            detail = f"module exited with code {exit_code}"
            self._emit_failed(f"{detail}: {error_text}" if error_text else detail)
            return
        try:
            result = self._load_and_validate_result()
        except (OSError, UnicodeError, ValidationError, ValueError) as exc:
            self._emit_failed(str(exc))
            return
        self._terminal_emitted = True
        self.completed.emit(result)

    def _load_and_validate_result(self) -> ModuleResult:
        if self._job is None or self._module is None:
            raise ValueError("runner lost job or module identity")
        output_dir = Path(self._job.output_dir).resolve()
        result_path = output_dir / "result.json"
        if not result_path.is_file():
            raise ValueError("result.json is missing")
        try:
            result = ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        except (UnicodeError, ValidationError) as exc:
            raise ValueError(f"invalid result.json: {exc}") from exc
        if result.job_id != self._job.job_id:
            raise ValueError("result job_id does not match job request")
        if result.module_id != self._module.manifest.module_id:
            raise ValueError("result module_id does not match registered module")

        for output in result.outputs:
            artifact = Path(output.path).resolve()
            if not artifact.is_relative_to(output_dir):
                raise ValueError("output artifact is outside output_dir")
            if not artifact.is_file():
                raise ValueError("output artifact is not a file")

        input_files = {Path(path).resolve() for path in self._job.input_files}
        for file_result in result.file_results:
            if Path(file_result.source_file).resolve() not in input_files:
                raise ValueError("file result source is not a job input")
        return result

    def _timeout(self) -> None:
        if self._terminal_emitted:
            return
        self._emit_failed("module timed out")
        self._stop_process()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if self._terminal_emitted:
            return
        self._emit_failed(f"module process error: {error.name}")
        self._stop_process()

    def _emit_failed(self, message: str) -> None:
        if self._terminal_emitted:
            return
        self._terminal_emitted = True
        self.timer.stop()
        self.failed.emit(message)

    def _stop_process(self) -> None:
        if not self.is_running:
            return
        self.process.terminate()
        self._kill_timer.start(self.cancellation_grace_ms)

    def _force_kill(self) -> None:
        if self.is_running:
            self.process.kill()
