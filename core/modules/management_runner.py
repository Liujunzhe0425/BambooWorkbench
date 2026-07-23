import logging
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from core.contracts.management import (
    ModuleManagementRequest,
    ModuleManagementResponse,
)
from core.platform.path_safety import (
    resolve_contained_directory,
    resolve_contained_file,
    resolve_contained_target,
)

from .host_runtime import add_packaged_host_environment, module_host_command
from .process_control import terminate_process
from .progress_parser import parse_progress
from .registry import RegisteredModule

_LOG = logging.getLogger("bamboo_workbench")


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class ModuleManagementRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        timeout_ms: int = 60_000,
        cancellation_grace_ms: int = 500,
        process_factory: Callable[[QObject], QProcess] = QProcess,
    ) -> None:
        super().__init__()
        self.timeout_ms = timeout_ms
        self.cancellation_grace_ms = cancellation_grace_ms
        self._process_factory = process_factory
        self._process: QProcess | None = None
        self._request: ModuleManagementRequest | None = None
        self._workspace: Path | None = None
        self._stdout_buffer = bytearray()
        self._pending_terminal: tuple[str, object | None] | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None

    def start(
        self,
        module: RegisteredModule,
        request: ModuleManagementRequest,
        workspace: Path,
    ) -> None:
        if self.is_running:
            raise RuntimeError("module management process is already active")
        entrypoint_name = module.manifest.management_entrypoint
        if not entrypoint_name:
            self.failed.emit("当前模块尚未提供资料管理入口")
            return
        try:
            workspace = resolve_contained_directory(
                workspace,
                workspace.parent,
                "management workspace",
                reject_link=True,
            )
            entrypoint = resolve_contained_file(
                module.path / entrypoint_name,
                module.path,
                "management entrypoint",
                reject_link=True,
            )
            request_path = resolve_contained_target(
                workspace / "request.json",
                workspace,
                "management request",
                reject_link=True,
            )
            response_path = resolve_contained_target(
                workspace / "response.json",
                workspace,
                "management response",
                reject_link=True,
            )
            _atomic_write(request_path, request.model_dump_json(indent=2))
            program, arguments = module_host_command(
                [
                    "--launcher",
                    str(entrypoint),
                    "manage",
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ]
            )
        except (OSError, ValueError) as error:
            _LOG.warning("module management launch rejected error_type=%s", type(error).__name__)
            self.failed.emit("无法启动模块资料管理，请查看应用日志")
            return

        process = self._process_factory(self)
        self._process = process
        self._request = request
        self._workspace = workspace
        self._stdout_buffer.clear()
        self._pending_terminal = None
        process.readyReadStandardOutput.connect(lambda: self._read_stdout(process))
        process.finished.connect(
            lambda exit_code, status: self._finished(process, exit_code, status)
        )
        process.errorOccurred.connect(lambda error: self._process_error(process, error))
        process.setProcessEnvironment(self._environment(request, module))
        process.setWorkingDirectory(str(module.path))
        process.start(program, arguments)
        QTimer.singleShot(self.timeout_ms, lambda: self._timeout(process))

    def cancel(self) -> bool:
        process = self._process
        if process is None or self._pending_terminal is not None:
            return False
        if process.state() == QProcess.ProcessState.NotRunning:
            return False
        self._pending_terminal = ("cancelled", None)
        process.terminate()
        QTimer.singleShot(self.cancellation_grace_ms, lambda: self._force_kill(process))
        return True

    def shutdown(self, timeout_ms: int = 3_000) -> bool:
        process = self._process
        if process is None:
            return True
        result = terminate_process(
            process,
            grace_ms=min(self.cancellation_grace_ms, timeout_ms),
            force_ms=max(timeout_ms - self.cancellation_grace_ms, 0),
        )
        self._clear(process)
        return result.process_stopped

    def _environment(
        self,
        request: ModuleManagementRequest,
        module: RegisteredModule,
    ) -> QProcessEnvironment:
        environment = QProcessEnvironment.systemEnvironment()
        runtime_dir = str(Path(sys.executable).resolve().parent)
        inherited_path = environment.value("PATH")
        environment.insert("PATH", f"{runtime_dir};{inherited_path}")
        environment.insert("PYTHONPATH", str(Path(__file__).parents[2]))
        environment.insert("PYTHONUTF8", "1")
        environment.insert("BAMBOO_MODULE_DATA_DIR", request.data_dir)
        module_key = module.manifest.module_id.value.upper()
        environment.insert(f"BAMBOO_{module_key}_DATA_DIR", request.data_dir)
        add_packaged_host_environment(environment)
        return environment

    def _read_stdout(self, process: QProcess) -> None:
        if self._process is not process:
            return
        self._stdout_buffer.extend(bytes(process.readAllStandardOutput()))
        if self._pending_terminal is not None:
            return
        while (newline := self._stdout_buffer.find(b"\n")) >= 0:
            line = bytes(self._stdout_buffer[: newline + 1])
            del self._stdout_buffer[: newline + 1]
            try:
                event = parse_progress(line)
            except (UnicodeError, ValidationError, ValueError):
                self._pending_terminal = ("failed", "模块资料管理返回了无效进度信息")
                process.terminate()
                QTimer.singleShot(
                    self.cancellation_grace_ms,
                    lambda: self._force_kill(process),
                )
                return
            self.progress.emit(event)

    def _finished(
        self,
        process: QProcess,
        exit_code: int,
        _status: QProcess.ExitStatus,
    ) -> None:
        if self._process is not process:
            return
        self._read_stdout(process)
        if self._pending_terminal is not None:
            kind, payload = self._pending_terminal
            self._emit_terminal(process, kind, payload)
            return
        if self._stdout_buffer:
            self._emit_terminal(process, "failed", "模块资料管理返回了不完整进度信息")
            return
        if exit_code != 0:
            _LOG.warning("module management exited with code=%d", exit_code)
            self._emit_terminal(process, "failed", "模块资料操作失败，请查看应用日志")
            return
        try:
            response = self._load_response()
        except (OSError, UnicodeError, ValidationError, ValueError) as error:
            _LOG.warning("module management response rejected error=%s", error)
            self._emit_terminal(process, "failed", "模块资料操作返回无效结果")
            return
        if response.status == "error":
            self._emit_terminal(process, "failed", response.message or "模块资料操作失败")
            return
        self._emit_terminal(process, "completed", response)

    def _load_response(self) -> ModuleManagementResponse:
        if self._workspace is None or self._request is None:
            raise ValueError("management runner lost request state")
        response_path = resolve_contained_file(
            self._workspace / "response.json",
            self._workspace,
            "management response",
            reject_link=True,
        )
        response = ModuleManagementResponse.model_validate_json(
            response_path.read_text(encoding="utf-8")
        )
        if (
            response.request_id != self._request.request_id
            or response.module_id is not self._request.module_id
            or response.operation is not self._request.operation
        ):
            raise ValueError("management response identity mismatch")
        return response

    def _timeout(self, process: QProcess) -> None:
        if self._process is not process or self._pending_terminal is not None:
            return
        self._pending_terminal = ("failed", "模块资料操作超时")
        process.terminate()
        QTimer.singleShot(
            self.cancellation_grace_ms,
            lambda: self._force_kill(process),
        )

    def _process_error(
        self,
        process: QProcess,
        _error: QProcess.ProcessError,
    ) -> None:
        if self._process is not process or self._pending_terminal is not None:
            return
        self._pending_terminal = ("failed", "模块资料管理进程无法启动")
        if process.state() == QProcess.ProcessState.NotRunning:
            self._emit_terminal(process, *self._pending_terminal)

    def _force_kill(self, process: QProcess) -> None:
        if (
            self._process is process
            and process.state() != QProcess.ProcessState.NotRunning
        ):
            process.kill()

    def _emit_terminal(self, process: QProcess, kind: str, payload: object | None) -> None:
        self._clear(process)
        if kind == "completed":
            self.completed.emit(payload)
        elif kind == "cancelled":
            self.cancelled.emit()
        else:
            self.failed.emit(str(payload))

    def _clear(self, process: QProcess) -> None:
        if self._process is not process:
            return
        self._process = None
        self._request = None
        self._workspace = None
        self._stdout_buffer.clear()
        self._pending_terminal = None
        process.deleteLater()
