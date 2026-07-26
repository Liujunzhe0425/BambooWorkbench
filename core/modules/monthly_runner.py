"""Isolated runner for the optional public monthly-rollup module contract."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError
from pydantic import ValidationError
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from core.contracts.monthly import MonthlyRollupRequest, MonthlyRollupResult
from core.platform.path_safety import resolve_contained_file, resolve_path

from .host_runtime import add_packaged_host_environment, module_host_command
from .process_control import terminate_process
from .registry import RegisteredModule

_SENSITIVE_ENVIRONMENT_MARKERS = (
    "API_KEY",
    "AUTHORIZATION",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)


class MonthlyRollupRunner(QObject):
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        timeout_ms: int = 180_000,
        process_factory: Callable[[QObject], QProcess] = QProcess,
    ) -> None:
        super().__init__()
        self.timeout_ms = timeout_ms
        self.process_factory = process_factory
        self._process: QProcess | None = None
        self._request: MonthlyRollupRequest | None = None
        self._module: RegisteredModule | None = None
        self._generation = 0

    @property
    def is_running(self) -> bool:
        return self._process is not None

    def start(self, module: RegisteredModule, request_path: Path) -> None:
        if self.is_running:
            raise RuntimeError("monthly rollup is already running")
        contract = module.manifest.monthly_rollup
        if contract is None or "monthly_rollup" not in module.manifest.capabilities:
            self.failed.emit("module does not declare the monthly_rollup contract")
            return
        try:
            trusted_request = resolve_path(request_path, "rollup request", strict=True)
            request = MonthlyRollupRequest.model_validate_json(
                trusted_request.read_text(encoding="utf-8")
            )
            request_schema = resolve_contained_file(
                module.path / contract.request_schema,
                module.path,
                "monthly request schema",
                reject_link=True,
            )
            Draft202012Validator(
                json.loads(request_schema.read_text(encoding="utf-8"))
            ).validate(request.model_dump(mode="json"))
            if request.module_id is not module.manifest.module_id:
                raise ValueError("rollup request module does not match registered module")
            if request.module_version != module.manifest.module_version:
                raise ValueError("rollup request version does not match registered module")
            self._validate_snapshot_integrity(request)
            entrypoint = resolve_path(
                module.path / contract.entrypoint, "monthly rollup entrypoint", strict=True
            )
            program, arguments = module_host_command(
                ["--launcher", str(entrypoint), "rollup", "--request", str(trusted_request)]
            )
        except (
            OSError,
            UnicodeError,
            ValidationError,
            JSONSchemaValidationError,
            ValueError,
        ) as error:
            self.failed.emit(f"invalid monthly rollup request: {error}")
            return

        self._generation += 1
        generation = self._generation
        process = self.process_factory(self)
        self._process = process
        self._request = request
        self._module = module
        process.finished.connect(
            lambda exit_code, status: self._finished(
                generation, process, exit_code, status
            )
        )
        process.errorOccurred.connect(
            lambda error: self._process_error(generation, process, error)
        )
        process.setProcessEnvironment(_offline_environment())
        process.setWorkingDirectory(str(module.path))
        process.start(program, arguments)
        QTimer.singleShot(self.timeout_ms, lambda: self._timeout(generation, process))

    def cancel(self) -> bool:
        process = self._process
        if process is None:
            return False
        generation = self._generation
        terminate_process(process, grace_ms=500, force_ms=2_500)
        if self._is_current(generation, process):
            self._clear(process)
            self.cancelled.emit()
        return True

    def shutdown(self, timeout_ms: int = 3_000) -> bool:
        process = self._process
        if process is None:
            return True
        result = terminate_process(process, grace_ms=500, force_ms=max(0, timeout_ms - 500))
        if result.process_stopped:
            self._clear(process)
        return result.process_stopped

    def _finished(
        self,
        generation: int,
        process: QProcess,
        exit_code: int,
        _status: QProcess.ExitStatus,
    ) -> None:
        if not self._is_current(generation, process):
            return
        if exit_code != 0:
            self._fail(process, f"monthly rollup exited with code {exit_code}")
            return
        try:
            result = self._load_result()
        except Exception as error:
            self._fail(process, f"invalid monthly rollup result: {error}")
            return
        self._clear(process)
        self.completed.emit(result)

    def _load_result(self) -> MonthlyRollupResult:
        if self._request is None or self._module is None:
            raise RuntimeError("monthly runner lost request identity")
        output_dir = resolve_path(
            Path(self._request.output_dir), "monthly output directory", strict=True
        )
        result_path = resolve_contained_file(
            output_dir / "rollup-result.json",
            output_dir,
            "monthly rollup result",
            reject_link=True,
        )
        raw = json.loads(result_path.read_text(encoding="utf-8"))
        contract = self._module.manifest.monthly_rollup
        assert contract is not None
        schema_path = resolve_contained_file(
            self._module.path / contract.response_schema,
            self._module.path,
            "monthly response schema",
            reject_link=True,
        )
        Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(raw)
        result = MonthlyRollupResult.model_validate(raw)
        if (
            result.transaction_id != self._request.transaction_id
            or result.module_id is not self._request.module_id
            or result.module_version != self._request.module_version
            or result.year != self._request.year
            or result.target_month != self._request.target_month
        ):
            raise ValueError("monthly rollup result identity mismatch")
        expected = {snapshot.snapshot_id: snapshot.sha256 for snapshot in self._request.snapshots}
        if result.used_snapshots != expected:
            raise ValueError("monthly rollup snapshot acknowledgement mismatch")
        for artifact in result.outputs:
            resolve_contained_file(
                Path(artifact.path), output_dir, "monthly output artifact", reject_link=True
            )
        return result

    @staticmethod
    def _validate_snapshot_integrity(request: MonthlyRollupRequest) -> None:
        for snapshot in request.snapshots:
            path = resolve_path(Path(snapshot.path), "monthly snapshot", strict=True)
            if not path.is_file() or path.is_symlink():
                raise ValueError("monthly snapshot is not a trusted file")
            if path.stat().st_size != snapshot.size:
                raise ValueError("monthly snapshot size mismatch")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != snapshot.sha256:
                raise ValueError("monthly snapshot hash mismatch")

    def _timeout(self, generation: int, process: QProcess) -> None:
        if not self._is_current(generation, process):
            return
        terminate_process(process, grace_ms=500, force_ms=2_500)
        if self._is_current(generation, process):
            self._fail(process, "monthly rollup timed out")

    def _process_error(
        self, generation: int, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if self._is_current(generation, process):
            self._fail(process, f"monthly rollup process error: {error.name}")

    def _fail(self, process: QProcess, message: str) -> None:
        self._clear(process)
        self.failed.emit(message)

    def _clear(self, process: QProcess) -> None:
        if self._process is process:
            self._process = None
            self._request = None
            self._module = None
            process.deleteLater()

    def _is_current(self, generation: int, process: QProcess) -> bool:
        return generation == self._generation and process is self._process


def _offline_environment() -> QProcessEnvironment:
    source = QProcessEnvironment.systemEnvironment()
    environment = QProcessEnvironment()
    for name in source:
        if any(marker in name.upper() for marker in _SENSITIVE_ENVIRONMENT_MARKERS):
            continue
        environment.insert(name, source.value(name))
    runtime_dir = str(Path(sys.executable).parent)
    environment.insert("PATH", f"{runtime_dir};{environment.value('PATH')}")
    environment.insert("PYTHONPATH", str(Path(__file__).parents[2]))
    environment.insert("PYTHONUTF8", "1")
    environment.insert("BAMBOO_OFFLINE", "1")
    environment.insert("NO_PROXY", "")
    environment.insert("HTTP_PROXY", "http://127.0.0.1:9")
    environment.insert("HTTPS_PROXY", "http://127.0.0.1:9")
    environment.insert("ALL_PROXY", "http://127.0.0.1:9")
    environment.insert("http_proxy", "http://127.0.0.1:9")
    environment.insert("https_proxy", "http://127.0.0.1:9")
    environment.insert("all_proxy", "http://127.0.0.1:9")
    environment.insert("no_proxy", "")
    if not getattr(sys, "frozen", False):
        environment.insert("BAMBOO_MODULE_PYTHON", str(Path(sys.executable).resolve()))
    add_packaged_host_environment(environment)
    return environment
