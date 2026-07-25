import json
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from core.contracts.enums import ModuleId
from core.contracts.management import (
    ModuleManagementOperation,
    ModuleManagementRequest,
    ModuleManagementResponse,
)
from core.platform.path_safety import (
    resolve_contained_directory,
    resolve_contained_file,
    resolve_contained_target,
    resolve_path,
)
from core.platform.paths import AppPaths

from .host_runtime import module_host_command
from .management_contract import ModuleManagementContractAdapter
from .management_runner import ModuleManagementRunner
from .progress_parser import parse_progress
from .registry import ModuleRegistry


class ModuleManagementService(QObject):
    progress = Signal(object, object)
    completed = Signal(object, object)
    failed = Signal(object, str)
    cancelled = Signal(object)

    def __init__(
        self,
        paths: AppPaths,
        registry: ModuleRegistry,
        runner_factory: Callable[[], ModuleManagementRunner] = ModuleManagementRunner,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.runner_factory = runner_factory
        self._runner: ModuleManagementRunner | None = None
        self._operation: ModuleManagementOperation | str | None = None
        self._workspace: Path | None = None

    @property
    def is_running(self) -> bool:
        return self._runner is not None

    def is_available(self, module_id: ModuleId) -> bool:
        if module_id is not ModuleId.MOISTURE:
            return False
        try:
            module = self.registry.get(module_id)
        except KeyError:
            return False
        return bool(
            "ai_report" in module.manifest.capabilities
            and module.manifest.management_entrypoint
        )

    def run(
        self,
        module_id: ModuleId,
        operation: ModuleManagementOperation,
        *,
        input_file: Path | None = None,
        history_id: str | None = None,
    ) -> str:
        if self.is_running:
            raise RuntimeError("已有模块资料操作正在运行")
        if module_id is not ModuleId.MOISTURE:
            raise RuntimeError("资料管理入口当前仅供竹丝水分 AI 汇总报告使用")
        module = self.registry.get(module_id)
        if (
            "ai_report" not in module.manifest.capabilities
            or not module.manifest.management_entrypoint
        ):
            raise RuntimeError("当前模块版本尚未提供历史资料与经验目录管理入口")
        self.paths.ensure()
        data_dir = self._module_data_dir(module_id)
        resolved_input: Path | None = None
        if input_file is not None:
            resolved_input = resolve_path(input_file, "history import file", strict=True)
            if _is_link(resolved_input) or not resolved_input.is_file():
                raise ValueError("历史汇总文件不可用")
            if resolved_input.suffix.casefold() != ".xlsx":
                raise ValueError("历史汇总只接受 .xlsx 文件")

        request_id = uuid4().hex
        workspace_root = self.paths.cache / "module-management"
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_root = resolve_contained_directory(
            workspace_root,
            self.paths.cache,
            "management workspace root",
            reject_link=True,
        )
        workspace = resolve_contained_target(
            workspace_root / request_id,
            workspace_root,
            "management workspace",
            reject_link=True,
        )
        workspace.mkdir()
        workspace = resolve_contained_directory(
            workspace,
            workspace_root,
            "management workspace",
            reject_link=True,
        )
        request = ModuleManagementRequest(
            schema_version="1.0",
            request_id=request_id,
            module_id=module_id,
            operation=operation,
            data_dir=str(data_dir),
            input_file=str(resolved_input) if resolved_input else None,
            history_id=history_id,
        )
        runner = self.runner_factory()
        self._runner = runner
        self._operation = operation
        self._workspace = workspace
        runner.progress.connect(lambda event: self.progress.emit(operation, event))
        runner.completed.connect(self._completed)
        runner.failed.connect(self._failed)
        runner.cancelled.connect(self._cancelled)
        runner.start(module, request, workspace)
        return request_id

    def run_custom(
        self,
        module_id: ModuleId,
        operation: str,
        parameters: dict[str, object] | None = None,
    ) -> str:
        if self.is_running:
            raise RuntimeError("已有模块资料操作正在运行")
        module = self.registry.get(module_id)
        if not module.manifest.management_entrypoint or not module.manifest.management_contract:
            raise RuntimeError("当前模块尚未提供版本化管理合同")
        request_id = uuid4().hex
        data_dir = self.data_dir(module_id)
        request = ModuleManagementContractAdapter(module).request(
            request_id=request_id,
            operation=operation,
            data_dir=data_dir,
            parameters=parameters,
        )
        workspace = self._new_workspace(request_id)
        runner = self.runner_factory()
        self._runner = runner
        self._operation = operation
        self._workspace = workspace
        runner.progress.connect(lambda event: self.progress.emit(operation, event))
        runner.completed.connect(self._completed)
        runner.failed.connect(self._failed)
        runner.cancelled.connect(self._cancelled)
        runner.start(module, request, workspace)
        return request_id

    def execute_sync(
        self,
        module_id: ModuleId,
        operation: str,
        parameters: dict[str, object] | None = None,
        *,
        timeout_seconds: float = 60.0,
    ) -> dict[str, object]:
        """Run a short framework-owned management query before task creation."""

        if self.is_running:
            raise RuntimeError("模块资料管理正在执行，暂时不能创建新任务")
        module = self.registry.get(module_id)
        descriptor = module.manifest.management_contract
        entrypoint_name = module.manifest.management_entrypoint
        if descriptor is None or not entrypoint_name:
            raise RuntimeError("当前模块尚未提供版本化管理合同")
        request_id = uuid4().hex
        data_dir = self.data_dir(module_id)
        adapter = ModuleManagementContractAdapter(module)
        request = adapter.request(
            request_id=request_id,
            operation=operation,
            data_dir=data_dir,
            parameters=parameters,
        )
        workspace = self._new_workspace(request_id)
        try:
            request_path = resolve_contained_target(
                workspace / "request.json", workspace, "management request", reject_link=True
            )
            response_path = resolve_contained_target(
                workspace / "response.json", workspace, "management response", reject_link=True
            )
            request_path.write_text(
                json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            entrypoint = resolve_contained_file(
                module.path / entrypoint_name,
                module.path,
                "management entrypoint",
                reject_link=True,
            )
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
            environment = dict(os.environ)
            environment["PYTHONUTF8"] = "1"
            environment["PYTHONPATH"] = str(Path(__file__).parents[2])
            environment["BAMBOO_MODULE_DATA_DIR"] = str(data_dir)
            environment[f"BAMBOO_{module_id.value.upper()}_DATA_DIR"] = str(data_dir)
            completed = subprocess.run(
                [program, *arguments],
                cwd=module.path,
                env=environment,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            for line in completed.stdout.splitlines(keepends=True):
                parse_progress(line)
            if completed.returncode != 0:
                raise RuntimeError("模块资料查询失败")
            payload = json.loads(
                resolve_contained_file(
                    response_path, workspace, "management response", reject_link=True
                ).read_text(encoding="utf-8")
            )
            response = adapter.validate_response(payload, request=request)
            if response.get("status") == "error":
                raise RuntimeError(str(response.get("message") or "模块资料查询失败"))
            return response
        except (OSError, UnicodeError, json.JSONDecodeError, subprocess.SubprocessError) as error:
            raise RuntimeError("模块资料查询失败") from error
        finally:
            shutil.rmtree(workspace, ignore_errors=True)

    def cancel(self) -> bool:
        return bool(self._runner and self._runner.cancel())

    def shutdown(self) -> bool:
        runner = self._runner
        if runner is None:
            return True
        stopped = runner.shutdown()
        self._cleanup()
        return stopped

    def data_dir(self, module_id: ModuleId) -> Path:
        self.paths.ensure()
        return self._module_data_dir(module_id)

    def _new_workspace(self, request_id: str) -> Path:
        workspace_root = self.paths.cache / "module-management"
        workspace_root.mkdir(parents=True, exist_ok=True)
        workspace_root = resolve_contained_directory(
            workspace_root,
            self.paths.cache,
            "management workspace root",
            reject_link=True,
        )
        workspace = resolve_contained_target(
            workspace_root / request_id,
            workspace_root,
            "management workspace",
            reject_link=True,
        )
        workspace.mkdir()
        return resolve_contained_directory(
            workspace,
            workspace_root,
            "management workspace",
            reject_link=True,
        )

    def _module_data_dir(self, module_id: ModuleId) -> Path:
        root = resolve_contained_directory(
            self.paths.module_data,
            self.paths.root,
            "module data root",
            reject_link=True,
        )
        target = resolve_contained_target(
            root / module_id.value,
            root,
            "module data directory",
            reject_link=True,
        )
        target.mkdir(exist_ok=True)
        return resolve_contained_directory(
            target,
            root,
            "module data directory",
            reject_link=True,
        )

    def _completed(self, response: ModuleManagementResponse | dict[str, object]) -> None:
        operation = self._operation
        self._cleanup()
        if operation is not None:
            self.completed.emit(operation, response)

    def _failed(self, message: str) -> None:
        operation = self._operation
        self._cleanup()
        if operation is not None:
            self.failed.emit(operation, message)

    def _cancelled(self) -> None:
        operation = self._operation
        self._cleanup()
        if operation is not None:
            self.cancelled.emit(operation)

    def _cleanup(self) -> None:
        workspace = self._workspace
        runner = self._runner
        self._runner = None
        self._operation = None
        self._workspace = None
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)
        if runner is not None:
            runner.deleteLater()


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())
