import hashlib
import json
import logging
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from core.contracts.confirmation import ConfirmationAnswer, ConfirmationBundle
from core.contracts.enums import JobPhase, ModuleId, RunMode, TaskStatus
from core.contracts.job import JobRequest
from core.contracts.result import ConfirmationPrompt, ModuleResult
from core.contracts.service_request import ServiceRequest
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry
from core.platform.path_safety import (
    resolve_contained_directory,
    resolve_contained_file,
    resolve_contained_target,
    resolve_path,
)
from core.platform.paths import AppPaths
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.tasks import TaskRepository
from core.storage.settings import SettingsStore
from core.tasks.job_builder import build_draft_job
from core.tasks.models import InvalidTaskTransition, TaskLifecycleState, TaskStateMachine
from core.tasks.output_publisher import publish_outputs
from core.tasks.result_status import normalized_result
from core.tasks.snapshots import remove_snapshots, snapshot_inputs

if TYPE_CHECKING:
    from core.modules.management_service import ModuleManagementService
    from core.services.orchestrator import ServiceOrchestrator
    from core.tasks.monthly_service import MonthlyRollupService

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{6,64}$")
_TERMINAL_MARKER = ".terminal-pending.json"
_SERVICE_CONSENT_PREFIX = "service-consent:"
_REDACTED_PREVIEW_MARKER = "[[REDACTED_PREVIEW]]"
_SENSITIVE_CONFIG_KEY = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|access[_-]?token)",
    re.IGNORECASE,
)
_LOG = logging.getLogger("bamboo_workbench")


def _new_job_id() -> str:
    return uuid4().hex


def _atomic_write_text(path: Path, content: str) -> None:
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


def _preview_record_count(payload: object) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 1
    for key in ("candidates", "records", "items", "rows", "cases"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 1


class TaskService(QObject):
    progress = Signal(str, object)
    finished = Signal(object)
    needs_confirmation = Signal(str, object)
    failed = Signal(str, str)
    orchestration_error = Signal(str, str)
    status_changed = Signal(str, str)
    publication_warning = Signal(str, str)

    def __init__(
        self,
        paths: AppPaths,
        registry: ModuleRegistry,
        task_repository: TaskRepository,
        confirmation_repository: ConfirmationRepository,
        runner_factory: Callable[[], ModuleProcessRunner] = ModuleProcessRunner,
        job_id_factory: Callable[[], str] = _new_job_id,
        service_orchestrator: "ServiceOrchestrator | None" = None,
        settings: SettingsStore | None = None,
        module_management_service: "ModuleManagementService | None" = None,
        monthly_rollup_service: "MonthlyRollupService | None" = None,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.task_repository = task_repository
        self.confirmation_repository = confirmation_repository
        self.runner_factory = runner_factory
        self.job_id_factory = job_id_factory
        self.service_orchestrator = service_orchestrator
        self.settings = settings
        self.module_management_service = module_management_service
        self.monthly_rollup_service = monthly_rollup_service
        self.runners: dict[str, ModuleProcessRunner] = {}
        self._states: dict[str, TaskStateMachine] = {}
        self._jobs: dict[str, JobRequest] = {}
        self._failed_signals: set[str] = set()
        self._cancellation_pending: set[str] = set()
        self._pending_confirmation_results: dict[str, ModuleResult] = {}
        self._shutdown = False
        self._shutdown_result = True
        self._blocked_callbacks: set[str] = set()
        self._preauthorized_ai: set[str] = set()
        if self.monthly_rollup_service is not None:
            self.monthly_rollup_service.completed.connect(self._monthly_completed)
            self.monthly_rollup_service.failed.connect(self._monthly_failed)
            self.monthly_rollup_service.detail_progress.connect(
                lambda job_id, event: self.progress.emit(job_id, event)
            )
        self._reconcile_startup()

    def pending_confirmations(self) -> list[tuple[str, ModuleResult]]:
        return sorted(self._pending_confirmation_results.items())

    def shutdown(self) -> bool:
        if self._shutdown:
            return self._shutdown_result
        self._shutdown = True
        cleanup_ok = True
        for job_id, runner in tuple(self.runners.items()):
            self._blocked_callbacks.add(job_id)
            try:
                shutdown = getattr(runner, "shutdown", None)
                stopped = bool(shutdown()) if callable(shutdown) else False
            except Exception as exc:
                _LOG.error("task shutdown runner fault job=%s error=%s", job_id, exc)
                stopped = False
            machine = self._states.get(job_id)
            if not stopped:
                cleanup_ok = False
                message = "module process cleanup failure during application shutdown"
                if machine is not None and machine.state in {
                    TaskLifecycleState.CREATED,
                    TaskLifecycleState.RUNNING_DRAFT,
                    TaskLifecycleState.RUNNING_FINALIZE,
                }:
                    try:
                        self._persist_transition(
                            job_id,
                            TaskLifecycleState.FAILED,
                            error=message,
                        )
                    except Exception as exc:
                        try:
                            self._write_terminal_marker(
                                job_id,
                                TaskLifecycleState.FAILED,
                                f"{message}: {exc}",
                            )
                        except Exception as marker_error:
                            _LOG.error(
                                "task shutdown persistence fault job=%s error=%s marker_error=%s",
                                job_id,
                                exc,
                                marker_error,
                            )
                _LOG.error("task process cleanup failure job=%s", job_id)
                continue
            if machine is not None and machine.state in {
                TaskLifecycleState.CREATED,
                TaskLifecycleState.RUNNING_DRAFT,
                TaskLifecycleState.RUNNING_FINALIZE,
            }:
                try:
                    self._persist_transition(
                        job_id,
                        TaskLifecycleState.CANCELLED,
                        error="application shutdown interrupted active task",
                    )
                except Exception as exc:
                    try:
                        self._write_terminal_marker(
                            job_id,
                            TaskLifecycleState.CANCELLED,
                            f"application shutdown interrupted active task: {exc}",
                        )
                    except Exception as marker_error:
                        _LOG.error(
                            "task shutdown persistence fault job=%s error=%s marker_error=%s",
                            job_id,
                            exc,
                            marker_error,
                        )
            self._cleanup_runner(job_id, runner, task_terminal=True)
            self._blocked_callbacks.discard(job_id)
        if self.monthly_rollup_service is not None:
            cleanup_ok = self.monthly_rollup_service.shutdown() and cleanup_ok
        self._shutdown_result = cleanup_ok
        if cleanup_ok:
            _LOG.info("task service shutdown complete")
        else:
            _LOG.error("task service shutdown completed with cleanup failure")
        return cleanup_ok

    def cancel(self, job_id: str) -> None:
        runner = self.runners.get(job_id)
        if runner is None:
            raise InvalidTaskTransition(f"job {job_id} has no active runner")
        if job_id in self._cancellation_pending:
            raise InvalidTaskTransition(f"job {job_id} cancellation is pending")
        self._cancellation_pending.add(job_id)
        try:
            accepted = runner.cancel()
        except Exception:
            self._cancellation_pending.discard(job_id)
            raise
        if not accepted:
            self._cancellation_pending.discard(job_id)
            raise InvalidTaskTransition(f"job {job_id} cancellation was not accepted")

    def create_and_start(
        self,
        module_id: ModuleId,
        inputs: list[Path],
        *,
        module_config: dict[str, object] | None = None,
        ai_consent_granted: bool = False,
        task_name: str | None = None,
        period_year: int | None = None,
        period_month: int | None = None,
        learning_enabled: bool = True,
    ) -> str:
        module = self.registry.get(module_id)
        framework_ai = module.manifest.framework_ai
        if framework_ai is not None and framework_ai.required and not ai_consent_granted:
            raise ValueError("当前模块必须先完成框架 AI 配置、连接测试和本批次授权")
        module_config = self._with_rule_snapshot(module_id, module, module_config)
        if module_config is not None:
            self._validate_module_config_support(
                module_id,
                module,
                module_config,
                input_count=len(inputs),
            )
        timestamp = datetime.now().astimezone()
        year = timestamp.year if period_year is None else period_year
        month = timestamp.month if period_month is None else period_month
        if not 2000 <= year <= 9999 or not 1 <= month <= 12:
            raise ValueError("任务年月无效")
        non_monthly_operation = (
            module_config is not None
            and module_config.get("operation") == "ai_report"
        )
        stored_year = None if non_monthly_operation else year
        stored_month = None if non_monthly_operation else month
        resolved_name = (
            task_name or f"{module.manifest.module_name}-{year}年{month:02d}月"
        ).strip()
        if not resolved_name or len(resolved_name) > 160:
            raise ValueError("任务名称不能为空且不能超过 160 个字符")
        output_root_id = None
        if self.monthly_rollup_service is not None:
            output_root_id = int(
                self.monthly_rollup_service.output_roots.current()["id"]
            )
        job_id = self.job_id_factory()
        if not _JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("job_id_factory returned an invalid job ID")
        self.paths.ensure()
        task_dir = self.paths.tasks / job_id
        task_dir.mkdir()
        try:
            self.task_repository.create(
                job_id,
                module_id.value,
                TaskLifecycleState.CREATED.value,
                timestamp.isoformat(),
                task_name=resolved_name,
                period_year=stored_year,
                period_month=stored_month,
                learning_enabled=learning_enabled,
                output_root_id=output_root_id,
            )
        except Exception:
            shutil.rmtree(task_dir)
            raise

        self._states[job_id] = TaskStateMachine()
        if ai_consent_granted:
            self._preauthorized_ai.add(job_id)
        runner: ModuleProcessRunner | None = None
        try:
            snapshots = snapshot_inputs(
                inputs,
                task_dir,
                supported_extensions=module.manifest.supported_extensions,
            )
            try:
                self.task_repository.add_files(
                    job_id,
                    [
                        (
                            str(snapshot.source),
                            str(snapshot.copy),
                            snapshot.fingerprint,
                            "snapshotted",
                        )
                        for snapshot in snapshots
                    ],
                )
            except Exception:
                remove_snapshots(snapshots)
                raise
            module_config_file: Path | None = None
            if module_config is not None:
                module_config_file = resolve_contained_target(
                    task_dir / "module-config.json",
                    task_dir,
                    "module configuration",
                    reject_link=True,
                )
                _atomic_write_text(
                    module_config_file,
                    self._module_config_text(module_config),
                )
            job = build_draft_job(
                job_id,
                module_id,
                [snapshot.copy for snapshot in snapshots],
                task_dir,
                module_config_file=module_config_file,
                task_name=resolved_name,
                period_year=stored_year,
                period_month=stored_month,
                learning_enabled=learning_enabled,
            )
            job_path = task_dir / "job-draft.json"
            job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
            self._jobs[job_id] = job
            self._persist_transition(job_id, TaskLifecycleState.RUNNING_DRAFT)
            runner = self.runner_factory()
            self.runners[job_id] = runner
            self._connect_runner(job_id, runner)
            self._start_runner(runner, module, job_path, job)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
        return job_id

    def finalize(self, job_id: str, bundle_path: Path) -> None:
        self._begin_finalize(job_id, bundle_path, validate_answers=True)

    def retry_monthly_rollup(self, job_id: str) -> None:
        if self.monthly_rollup_service is None:
            raise RuntimeError("月度累计框架服务未配置")
        task = self.task_repository.get(job_id)
        if task["status"] != TaskLifecycleState.REPLACEMENT_CANDIDATE.value:
            raise InvalidTaskTransition("只有替换候选任务可以重试累计生成")
        task_dir = resolve_contained_directory(
            self.paths.tasks / job_id,
            self.paths.tasks,
            "replacement candidate task directory",
            reject_link=True,
        )
        final_path = resolve_contained_file(
            task_dir / "job-finalize.json",
            task_dir,
            "replacement candidate final job",
            reject_link=True,
        )
        job = JobRequest.model_validate_json(final_path.read_text(encoding="utf-8"))
        result_path = resolve_contained_file(
            Path(job.output_dir) / "result.json",
            task_dir,
            "replacement candidate result",
            reject_link=True,
        )
        result = ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        self._states[job_id] = TaskStateMachine(TaskLifecycleState.REPLACEMENT_CANDIDATE)
        self._jobs[job_id] = job
        self._persist_transition(job_id, TaskLifecycleState.RUNNING_FINALIZE)
        try:
            self.monthly_rollup_service.start(job_id, result)
        except Exception as error:
            self._monthly_failed(job_id, self._error_message(error), True)

    def _begin_finalize(
        self,
        job_id: str,
        bundle_path: Path,
        *,
        validate_answers: bool,
    ) -> None:
        machine = self._states.get(job_id)
        if machine is None or machine.state is not TaskLifecycleState.WAITING_CONFIRMATION:
            current = machine.state.value if machine is not None else "terminal_or_unknown"
            raise InvalidTaskTransition(
                f"finalize requires waiting_confirmation, current state is {current}"
            )
        if job_id in self.runners:
            raise InvalidTaskTransition(f"job {job_id} already has an active runner")
        task = self.task_repository.get(job_id)
        if task["status"] != TaskLifecycleState.WAITING_CONFIRMATION.value:
            raise InvalidTaskTransition("persisted task state is not waiting_confirmation")

        tasks_root = resolve_path(self.paths.tasks, "tasks root", strict=True)
        if not tasks_root.is_dir():
            raise ValueError("tasks root is not a directory")
        task_dir = resolve_contained_directory(
            self.paths.tasks / job_id,
            tasks_root,
            "task directory",
            reject_link=True,
        )
        expected_bundle_path = task_dir / "confirmation.json"
        resolved_bundle_path = resolve_contained_file(
            bundle_path,
            task_dir,
            "confirmation file",
            reject_link=True,
        )
        if resolved_bundle_path != expected_bundle_path:
            raise ValueError("confirmation bundle is not the task-local confirmation.json")
        bundle = ConfirmationBundle.model_validate_json(
            resolved_bundle_path.read_text(encoding="utf-8")
        )
        if bundle.job_id != job_id:
            raise ValueError("confirmation bundle job_id does not match task")
        if validate_answers:
            self._validate_stored_answers(job_id, bundle)
        elif bundle.answers:
            raise ValueError("automatic service finalization requires an empty bundle")

        draft_path = resolve_contained_file(
            task_dir / "job-draft.json",
            task_dir,
            "draft job file",
            reject_link=True,
        )
        draft = JobRequest.model_validate_json(draft_path.read_text(encoding="utf-8"))
        trusted_draft = self._jobs.get(job_id)
        if trusted_draft is None:
            raise ValueError("trusted draft state is unavailable")
        if draft.model_dump(mode="json") != trusted_draft.model_dump(mode="json"):
            raise ValueError("job-draft file does not match trusted retained draft state")
        if trusted_draft.job_id != job_id or trusted_draft.phase is not JobPhase.DRAFT:
            raise ValueError("job-draft identity or phase does not match task")
        if trusted_draft.module_id.value != task["module_id"]:
            raise ValueError("job-draft module_id does not match persisted task")
        self._validate_draft_paths(job_id, task_dir, trusted_draft)
        frozen_bundle_path = resolve_contained_target(
            task_dir / "confirmation-finalize.json",
            task_dir,
            "frozen confirmation file",
            reject_link=True,
        )

        final_output_dir = resolve_contained_target(
            task_dir / "output-final",
            task_dir,
            "final output",
            reject_link=True,
        )
        if final_output_dir.exists() and not final_output_dir.is_dir():
            raise ValueError("final output must be a directory when it already exists")
        draft_result = self._load_draft_result(job_id, task_dir, trusted_draft)
        service_response_file: str | None = trusted_draft.service_response_file
        ai_consent: dict[str, bool] = {}
        if draft_result.service_requests:
            if self.service_orchestrator is None:
                raise RuntimeError("module requested shared services but none are configured")
            ai_consent = self._service_consent_map(
                job_id, bundle, draft_result.service_requests
            )
            response_path = self.service_orchestrator.resolve(
                task_id=job_id,
                module_id=trusted_draft.module_id.value,
                allowed_namespaces=set(trusted_draft.allowed_knowledge_scopes),
                requests=draft_result.service_requests,
                ai_consent=ai_consent,
                task_dir=task_dir,
                authorization_source=self._ai_authorization_source(job_id),
            )
            service_response_file = str(response_path)
        final_payload = trusted_draft.model_dump(mode="python")
        final_payload.update(
            phase=JobPhase.FINALIZE,
            parent_job_id=job_id,
            confirmation_file=str(frozen_bundle_path),
            output_dir=str(final_output_dir),
            service_response_file=service_response_file,
            ai_enabled=trusted_draft.ai_enabled or any(ai_consent.values()),
        )
        final_job = JobRequest.model_validate(final_payload)
        final_path = task_dir / "job-finalize.json"
        _atomic_write_text(frozen_bundle_path, bundle.model_dump_json(indent=2))
        _atomic_write_text(final_path, final_job.model_dump_json(indent=2))
        self.confirmation_repository.delete_draft(job_id)

        self._persist_transition(job_id, TaskLifecycleState.RUNNING_FINALIZE)
        self._pending_confirmation_results.pop(job_id, None)
        self._jobs[job_id] = final_job
        runner: ModuleProcessRunner | None = None
        try:
            runner = self.runner_factory()
            self.runners[job_id] = runner
            self._connect_runner(job_id, runner)
            self._start_runner(
                runner,
                self.registry.get(trusted_draft.module_id),
                final_path,
                final_job,
            )
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)

    def _validate_draft_paths(self, job_id: str, task_dir: Path, draft: JobRequest) -> None:
        persisted_files = self.task_repository.list_files(job_id)
        persisted_snapshots = [
            resolve_contained_file(
                Path(str(record["snapshot_path"])),
                task_dir,
                "persisted input snapshot",
                reject_link=True,
            )
            for record in persisted_files
        ]
        for record, snapshot in zip(persisted_files, persisted_snapshots, strict=True):
            if self._sha256(snapshot) != str(record["fingerprint"]):
                raise ValueError("persisted input snapshot fingerprint does not match content")
        draft_inputs = [
            resolve_contained_file(
                Path(path),
                task_dir,
                "draft input file",
                reject_link=True,
            )
            for path in draft.input_files
        ]
        if len(draft_inputs) != len(persisted_snapshots) or set(draft_inputs) != set(
            persisted_snapshots
        ):
            raise ValueError("job-draft input files do not match persisted snapshots")

        expected_output = resolve_contained_directory(
            task_dir / "output-draft",
            task_dir,
            "expected draft output",
            reject_link=True,
        )
        draft_output = resolve_contained_directory(
            Path(draft.output_dir),
            task_dir,
            "draft output",
            reject_link=True,
        )
        if draft_output != expected_output:
            raise ValueError("job-draft output does not match task-local draft output")

        expected_mode = RunMode.SINGLE if len(draft_inputs) == 1 else RunMode.BATCH
        if draft.run_mode is not expected_mode:
            raise ValueError("job-draft run_mode does not match persisted snapshot count")
        service_bound = draft.service_response_file is not None
        if draft.ai_enabled and not service_bound:
            raise ValueError("job-draft AI state does not match its service response")
        if draft.allowed_knowledge_scopes != ["shared", draft.module_id.value]:
            raise ValueError("job-draft knowledge scopes are not canonical")
        if draft.module_config_file is not None:
            expected_config = resolve_contained_file(
                task_dir / "module-config.json",
                task_dir,
                "module configuration",
                reject_link=True,
            )
            actual_config = resolve_contained_file(
                Path(draft.module_config_file),
                task_dir,
                "module configuration",
                reject_link=True,
            )
            if actual_config != expected_config:
                raise ValueError("job-draft module configuration is not canonical")
            payload = json.loads(actual_config.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("module configuration must be a JSON object")
            self._module_config_text(payload)
        if service_bound:
            response = resolve_contained_file(
                Path(str(draft.service_response_file)),
                task_dir,
                "draft service response",
                reject_link=True,
            )
            expected_protocol = resolve_contained_directory(
                task_dir / "protocol",
                task_dir,
                "service protocol directory",
                reject_link=True,
            )
            if response.parent != expected_protocol:
                raise ValueError("draft service response is outside the protocol directory")
        if draft.parent_job_id is not None or draft.confirmation_file is not None:
            raise ValueError("job-draft finalize-only fields must be empty")

    def _start_runner(
        self,
        runner: ModuleProcessRunner,
        module: object,
        job_path: Path,
        job: JobRequest,
    ) -> None:
        if job.module_config_file is not None:
            data_dir = self._module_data_dir(job.module_id)
            configure = getattr(runner, "set_environment_overrides", None)
            if callable(configure):
                module_key = job.module_id.value.upper()
                configure(
                    {
                        "BAMBOO_MODULE_DATA_DIR": str(data_dir),
                        f"BAMBOO_{module_key}_DATA_DIR": str(data_dir),
                    }
                )
        runner.start(module, job_path)

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

    @staticmethod
    def _module_config_text(payload: dict[str, object]) -> str:
        if not isinstance(payload, dict):
            raise ValueError("module configuration must be a JSON object")

        def visit(value: object) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(key, str) or _SENSITIVE_CONFIG_KEY.search(key):
                        raise ValueError("module configuration contains a forbidden key")
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(payload)
        content = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
        if len(content.encode("utf-8")) > 65_536:
            raise ValueError("module configuration exceeds 65536 bytes")
        return content

    @staticmethod
    def _validate_module_config_support(
        module_id: ModuleId,
        module: object,
        payload: dict[str, object],
        *,
        input_count: int,
    ) -> None:
        manifest = getattr(module, "manifest", None)
        capabilities = getattr(manifest, "capabilities", [])
        if module_id is not ModuleId.MOISTURE or payload.get("schema_version") != "1.0":
            raise ValueError("当前模块不支持该任务配置")
        operation = payload.get("operation")
        if operation is None and set(payload) <= {"schema_version", "rule_selection"}:
            return
        if operation == "summary" and set(payload) <= {
            "schema_version",
            "operation",
            "default_year",
            "rule_selection",
        }:
            return
        if operation == "ai_report":
            if "ai_report" not in capabilities:
                raise ValueError("当前模块版本不支持独立 AI 汇总报告")
            return
        if operation != "append_summary":
            raise ValueError("水分模块任务配置的操作类型无效")
        manifest = getattr(module, "manifest", None)
        if not getattr(manifest, "supports_incremental", False):
            raise ValueError("当前水分模块尚未声明支持历史汇总追加")
        inputs = payload.get("inputs")
        if (
            not isinstance(inputs, list)
            or len(inputs) < 2
            or len(inputs) != input_count
        ):
            raise ValueError("历史追加至少需要一份历史汇总表和一份新原始数据")
        expected_indexes = set(range(len(inputs)))
        actual_indexes: set[int] = set()
        base_count = 0
        for item in inputs:
            if not isinstance(item, dict) or set(item) != {"role", "input_index"}:
                raise ValueError("历史追加输入角色配置无效")
            role = item.get("role")
            index = item.get("input_index")
            if role not in {"base_summary", "new_raw"} or type(index) is not int:
                raise ValueError("历史追加输入角色或序号无效")
            actual_indexes.add(index)
            base_count += int(role == "base_summary")
        if base_count != 1 or actual_indexes != expected_indexes:
            raise ValueError("历史追加必须完整且不重复地分配一份基表和全部新数据")

    def _with_rule_snapshot(
        self,
        module_id: ModuleId,
        module: object,
        module_config: dict[str, object] | None,
    ) -> dict[str, object] | None:
        manifest = getattr(module, "manifest", None)
        capabilities = getattr(manifest, "capabilities", [])
        if module_id is not ModuleId.MOISTURE or "rule_snapshot" not in capabilities:
            return module_config
        management = self.module_management_service
        temporary_management = False
        if management is None:
            from core.modules.management_service import ModuleManagementService

            management = ModuleManagementService(self.paths, self.registry)
            temporary_management = True
        try:
            response = management.execute_sync(
                module_id,
                "get_active_rule_identity",
                {},
            )
        finally:
            if temporary_management:
                management.shutdown()
        result = response.get("result")
        active = result.get("active_rule") if isinstance(result, dict) else None
        if not isinstance(active, dict) or set(active) != {"version", "sha256"}:
            raise RuntimeError("水分模块没有返回有效的当前规则身份")
        version = active.get("version")
        sha256 = active.get("sha256")
        if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", version):
            raise RuntimeError("当前规则版本无效")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise RuntimeError("当前规则哈希无效")
        configured = dict(
            module_config
            or {
                "schema_version": "1.0",
                "operation": "summary",
            }
        )
        configured.setdefault("schema_version", "1.0")
        existing = configured.get("rule_selection")
        selection = {"version": version, "sha256": sha256}
        if existing is not None and existing != selection:
            raise ValueError("任务配置中的规则快照与当前有效规则不一致")
        configured["rule_selection"] = selection
        return configured

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _validate_stored_answers(self, job_id: str, bundle: ConfirmationBundle) -> None:
        records = self.confirmation_repository.list_for_job(job_id)
        if not records:
            raise ValueError("stored answered state has no canonical prompts")
        prompts = {
            prompt.confirmation_id: prompt
            for prompt in (
                ConfirmationPrompt.model_validate(record["original_prompt"]) for record in records
            )
        }
        bundle_ids = [answer.confirmation_id for answer in bundle.answers]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("confirmation bundle has duplicate answer IDs")
        unknown = set(bundle_ids) - set(prompts)
        if unknown:
            raise ValueError(f"confirmation bundle has unknown answer IDs: {sorted(unknown)}")

        stored_answers = {
            str(record["confirmation_id"]): ConfirmationAnswer.model_validate(record["answer"])
            for record in records
            if record["answer"] is not None
        }
        required = {
            confirmation_id for confirmation_id, prompt in prompts.items() if prompt.blocking
        }
        if required - set(stored_answers):
            raise ValueError("stored answered state is missing blocking confirmations")
        supplied = {answer.confirmation_id: answer for answer in bundle.answers}
        if required - set(supplied):
            raise ValueError("confirmation bundle is missing blocking confirmations")
        if stored_answers != supplied:
            raise ValueError("confirmation bundle does not match stored answered state")

    def _connect_runner(self, job_id: str, runner: ModuleProcessRunner) -> None:
        runner.progress.connect(
            lambda event, active=runner: self._forward_progress(job_id, event, active)
        )
        runner.completed.connect(
            lambda result, active=runner: self._complete(job_id, result, active)
        )
        runner.failed.connect(
            lambda message, active=runner: self._record_failure(job_id, str(message), active)
        )
        runner.cancelled.connect(lambda active=runner: self._cancelled(job_id, active))

    def _forward_progress(self, job_id: str, event: object, runner: ModuleProcessRunner) -> None:
        if job_id in self._blocked_callbacks:
            return
        if self.runners.get(job_id) is runner:
            self.progress.emit(job_id, event)

    def _complete(self, job_id: str, result: ModuleResult, runner: ModuleProcessRunner) -> None:
        if job_id in self._blocked_callbacks:
            return
        if self.runners.get(job_id) is not runner:
            return
        auto_finalize = False
        try:
            job = self._jobs[job_id]
            result_path = str((Path(job.output_dir) / "result.json").resolve())
            if job.phase is JobPhase.DRAFT:
                if job.service_response_file is None and result.service_requests:
                    self._cleanup_runner(job_id, runner, task_terminal=False)
                    self._start_service_bound_draft(job_id, job, result)
                    return
                if (
                    self._service_first_required(job)
                    and
                    job.service_response_file is None
                    and result.summary.processed_count > 0
                    and not result.service_requests
                ):
                    raise RuntimeError("售后模块未为成功解析的文件生成 AI 服务请求")
            pending = (
                self._prepare_pending_result(job_id, job, result)
                if job.phase is JobPhase.DRAFT
                else None
            )
            if pending is not None:
                if pending.confirmations:
                    self.confirmation_repository.save_prompts(job_id, pending.confirmations)
                self._persist_transition(
                    job_id,
                    TaskLifecycleState.WAITING_CONFIRMATION,
                    result_path=result_path,
                )
                self._pending_confirmation_results[job_id] = pending
                if pending.confirmations:
                    self.needs_confirmation.emit(job_id, pending)
                else:
                    auto_finalize = True
                task_terminal = False
            else:
                host_result = normalized_result(result)
                if host_result.status is not result.status:
                    _LOG.warning(
                        "module task status normalized job=%s module_status=%s host_status=%s",
                        job_id,
                        result.status.value,
                        host_result.status.value,
                    )
                target = TaskLifecycleState(host_result.status.value)
                display_result = host_result
                if host_result.status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
                    module = self.registry.get(job.module_id)
                    if (
                        job.phase is JobPhase.FINALIZE
                        and module.manifest.monthly_rollup is not None
                        and host_result.monthly_snapshot is not None
                    ):
                        if self.monthly_rollup_service is None:
                            raise RuntimeError("月度累计框架服务未配置")
                        self._cleanup_runner(job_id, runner, task_terminal=False)
                        self.monthly_rollup_service.start(job_id, host_result)
                        return
                    display_result = self._publish_result(job_id, job, host_result)
                    self.task_repository.replace_outputs(job_id, display_result.outputs)
                self._persist_transition(job_id, target, result_path=result_path)
                _LOG.info("task terminal job=%s status=%s", job_id, target.value)
                self.finished.emit(display_result)
                task_terminal = True
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
            return
        self._cleanup_runner(job_id, runner, task_terminal=task_terminal)
        if auto_finalize:
            try:
                self._auto_finalize_services(job_id)
            except Exception as exc:
                self._record_failure(job_id, self._error_message(exc))

    def _monthly_completed(self, job_id: str, result: ModuleResult) -> None:
        try:
            target = TaskLifecycleState(result.status.value)
            result_path = str((Path(self._jobs[job_id].output_dir) / "result.json").resolve())
            self._persist_transition(job_id, target, result_path=result_path)
            self.finished.emit(result)
            _LOG.info("monthly rollup committed job=%s status=%s", job_id, target.value)
        except Exception as error:
            self._record_failure(job_id, self._error_message(error))
            return
        self._cleanup_runner(job_id, task_terminal=True)

    def _monthly_failed(
        self, job_id: str, message: str, replacement_candidate: bool
    ) -> None:
        target = (
            TaskLifecycleState.REPLACEMENT_CANDIDATE
            if replacement_candidate
            else TaskLifecycleState.FAILED
        )
        try:
            self._persist_transition(job_id, target, error=message)
        except Exception as error:
            self._record_failure(job_id, self._error_message(error))
            return
        self.failed.emit(job_id, message)
        self._cleanup_runner(job_id, task_terminal=True)

    def _service_first_required(self, job: JobRequest) -> bool:
        module = self.registry.get(job.module_id)
        policy = module.manifest.framework_ai
        return bool(policy and policy.required and policy.service_before_confirmation)

    def _start_service_bound_draft(
        self,
        job_id: str,
        draft: JobRequest,
        result: ModuleResult,
    ) -> None:
        if self.service_orchestrator is None:
            raise RuntimeError("框架 AI 服务尚未配置")
        task_dir = resolve_contained_directory(
            self.paths.tasks / job_id,
            self.paths.tasks,
            "service-first task directory",
            reject_link=True,
        )
        allowed = bool(
            (self.settings and self.settings.get("ai_network_enabled", "false") == "true")
            or job_id in self._preauthorized_ai
        )
        decisions = {
            request.request_id: allowed
            for request in result.service_requests
            if request.service == "ai"
        }
        response_path = self.service_orchestrator.resolve(
            task_id=job_id,
            module_id=draft.module_id.value,
            allowed_namespaces=set(draft.allowed_knowledge_scopes),
            requests=result.service_requests,
            ai_consent=decisions,
            task_dir=task_dir,
            authorization_source=self._ai_authorization_source(job_id),
        )
        rebound_payload = draft.model_dump(mode="python")
        rebound_payload.update(
            service_response_file=str(response_path),
            ai_enabled=allowed and bool(decisions),
        )
        rebound = JobRequest.model_validate(rebound_payload)
        draft_path = resolve_contained_target(
            task_dir / "job-draft.json",
            task_dir,
            "service-bound draft job",
            reject_link=True,
        )
        _atomic_write_text(draft_path, rebound.model_dump_json(indent=2))
        self._jobs[job_id] = rebound
        next_runner = self.runner_factory()
        self.runners[job_id] = next_runner
        self._connect_runner(job_id, next_runner)
        self._start_runner(
            next_runner,
            self.registry.get(draft.module_id),
            draft_path,
            rebound,
        )

    def _publish_result(
        self,
        job_id: str,
        job: JobRequest,
        result: ModuleResult,
    ) -> ModuleResult:
        configured_root = (
            self.settings.get("output_dir", str(self.paths.output))
            if self.settings
            else str(self.paths.output)
        ) or str(self.paths.output)
        try:
            task = self.task_repository.get(job_id)
            published = publish_outputs(
                result,
                task_name=str(task.get("task_name") or "").strip() or None,
                task_number=self.task_repository.get_number(job_id),
                task_dir=self.paths.tasks / job_id,
                task_output_dir=Path(job.output_dir),
                configured_root=configured_root,
                folder_timestamp=datetime.fromisoformat(str(task["created_at"])),
            )
        except Exception as error:
            message = (
                "成果已保留在本机任务目录，但复制到设置的输出目录失败："
                f"{type(error).__name__}: {error}"
            )
            _LOG.warning("task output publication failed job=%s error=%s", job_id, error)
            self.publication_warning.emit(job_id, message)
            return result
        _LOG.info(
            "task outputs published job=%s output_count=%d",
            job_id,
            len(published.outputs),
        )
        return published

    def _cancelled(self, job_id: str, runner: ModuleProcessRunner) -> None:
        if job_id in self._blocked_callbacks:
            return
        if self.runners.get(job_id) is not runner:
            return
        try:
            self._persist_transition(job_id, TaskLifecycleState.CANCELLED)
            _LOG.info("task terminal job=%s status=cancelled", job_id)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
            return
        self._cleanup_runner(job_id, runner, task_terminal=True)

    def _record_failure(
        self,
        job_id: str,
        message: str,
        runner: ModuleProcessRunner | None = None,
    ) -> None:
        if job_id in self._blocked_callbacks:
            return
        if runner is not None and self.runners.get(job_id) is not runner:
            return
        if job_id in self._failed_signals:
            self._cleanup_runner(job_id, runner, task_terminal=True)
            return
        try:
            self._persist_transition(job_id, TaskLifecycleState.FAILED, error=message)
        except Exception as persistence_error:
            marker_error: Exception | None = None
            try:
                self._write_terminal_marker(job_id, TaskLifecycleState.FAILED, message)
            except Exception as exc:
                marker_error = exc
            self._cleanup_runner(job_id, runner, task_terminal=True)
            self.orchestration_error.emit(
                job_id,
                f"{message}; failed to persist failed task state: "
                f"{type(persistence_error).__name__}: {persistence_error}"
                + (
                    f"; failed to persist terminal marker: {type(marker_error).__name__}: "
                    f"{marker_error}"
                    if marker_error is not None
                    else ""
                ),
            )
            _LOG.error("task orchestration persistence fault job=%s error=%s", job_id, message)
            return
        self._failed_signals.add(job_id)
        self.failed.emit(job_id, message)
        _LOG.error("task failed job=%s error=%s", job_id, message)
        self._cleanup_runner(job_id, runner, task_terminal=True)

    def _persist_transition(
        self,
        job_id: str,
        target: TaskLifecycleState,
        *,
        error: str | None = None,
        result_path: str | None = None,
    ) -> None:
        machine = self._states[job_id]
        machine.ensure_transition(target)
        self.task_repository.update_status(
            job_id,
            target.value,
            error=error,
            result_path=result_path,
        )
        machine.transition(target)
        self.status_changed.emit(job_id, target.value)

    def _cleanup_runner(
        self,
        job_id: str,
        runner: ModuleProcessRunner | None = None,
        *,
        task_terminal: bool = False,
    ) -> None:
        active = self.runners.get(job_id)
        if runner is not None and active is not runner:
            return
        removed = self.runners.pop(job_id, None)
        self._cancellation_pending.discard(job_id)
        if removed is not None:
            removed.deleteLater()
        if task_terminal:
            self._states.pop(job_id, None)
            self._jobs.pop(job_id, None)
            self._pending_confirmation_results.pop(job_id, None)
            self._failed_signals.discard(job_id)
            self._preauthorized_ai.discard(job_id)

    def _write_terminal_marker(
        self,
        job_id: str,
        status: TaskLifecycleState,
        error: str,
    ) -> None:
        if not _JOB_ID_PATTERN.fullmatch(job_id):
            raise ValueError("invalid job ID for terminal marker")
        tasks_root = resolve_contained_directory(
            self.paths.tasks,
            self.paths.root,
            "tasks root",
            reject_link=True,
        )
        task_dir = resolve_contained_directory(
            self.paths.tasks / job_id,
            tasks_root,
            "terminal marker task directory",
            reject_link=True,
        )
        marker = resolve_contained_target(
            task_dir / _TERMINAL_MARKER,
            task_dir,
            "terminal marker target",
            reject_link=True,
        )
        payload = {"job_id": job_id, "status": status.value, "error": error}
        _atomic_write_text(marker, json.dumps(payload, ensure_ascii=False, indent=2))

    def _reconcile_startup(self) -> None:
        self.paths.ensure()
        self._apply_terminal_markers()
        active_statuses = (
            TaskLifecycleState.CREATED.value,
            TaskLifecycleState.RUNNING_DRAFT.value,
            TaskLifecycleState.RUNNING_FINALIZE.value,
            TaskLifecycleState.WAITING_CONFIRMATION.value,
        )
        for task in self.task_repository.list_by_status(active_statuses):
            job_id = str(task["job_id"])
            status = str(task["status"])
            if status == TaskLifecycleState.WAITING_CONFIRMATION.value:
                try:
                    self._recover_waiting_confirmation(task)
                except Exception as exc:
                    self.task_repository.update_status(
                        job_id,
                        TaskLifecycleState.FAILED.value,
                        error=f"interrupted waiting-confirmation recovery failed: {exc}",
                    )
                    _LOG.error("task recovery failed job=%s error=%s", job_id, exc)
                continue
            self.task_repository.update_status(
                job_id,
                TaskLifecycleState.FAILED.value,
                error=f"interrupted application restart from {status}",
            )
            _LOG.warning("task reconciled as interrupted job=%s prior_status=%s", job_id, status)

    def _apply_terminal_markers(self) -> None:
        try:
            tasks_root = resolve_contained_directory(
                self.paths.tasks,
                self.paths.root,
                "tasks root",
                reject_link=True,
            )
            candidates = tuple(tasks_root.iterdir())
        except Exception as exc:
            _LOG.error("terminal marker tasks-root fault error=%s", exc)
            return
        allowed_sources = {
            TaskLifecycleState.CREATED.value,
            TaskLifecycleState.RUNNING_DRAFT.value,
            TaskLifecycleState.RUNNING_FINALIZE.value,
        }
        for candidate in candidates:
            marker = candidate / _TERMINAL_MARKER
            try:
                job_id = candidate.name
                if not _JOB_ID_PATTERN.fullmatch(job_id):
                    continue
                task_dir = resolve_contained_directory(
                    candidate,
                    tasks_root,
                    "terminal marker task directory",
                    reject_link=True,
                )
                marker = task_dir / _TERMINAL_MARKER
                if not marker.exists():
                    continue
                marker = resolve_contained_file(
                    marker,
                    task_dir,
                    "terminal marker file",
                    reject_link=True,
                )
                payload = json.loads(marker.read_text(encoding="utf-8"))
                if not isinstance(payload, dict) or set(payload) != {
                    "job_id",
                    "status",
                    "error",
                }:
                    raise ValueError("terminal marker payload keys are invalid")
                payload_job_id = payload["job_id"]
                payload_status = payload["status"]
                error = payload["error"]
                if not all(
                    isinstance(value, str) for value in (payload_job_id, payload_status, error)
                ):
                    raise ValueError("terminal marker payload values must be strings")
                if not _JOB_ID_PATTERN.fullmatch(payload_job_id):
                    raise ValueError("terminal marker job ID is invalid")
                status = TaskLifecycleState(payload_status)
                if payload_job_id != job_id or status not in {
                    TaskLifecycleState.FAILED,
                    TaskLifecycleState.CANCELLED,
                }:
                    raise ValueError("invalid terminal marker identity or status")
                task = self.task_repository.get(job_id)
                if task["status"] not in allowed_sources:
                    raise ValueError("terminal marker cannot overwrite persisted task status")
                self.task_repository.update_status(job_id, status.value, error=error)
                marker.unlink()
                _LOG.warning("terminal marker applied job=%s status=%s", job_id, status.value)
            except Exception as exc:
                _LOG.error("terminal marker recovery fault path=%s error=%s", marker, exc)

    def _recover_waiting_confirmation(self, task: dict[str, object]) -> None:
        job_id = str(task["job_id"])
        tasks_root = resolve_path(self.paths.tasks, "tasks root", strict=True)
        task_dir = resolve_contained_directory(
            self.paths.tasks / job_id,
            tasks_root,
            "task directory",
            reject_link=True,
        )
        draft_path = resolve_contained_file(
            task_dir / "job-draft.json",
            task_dir,
            "draft job file",
            reject_link=True,
        )
        draft = JobRequest.model_validate_json(draft_path.read_text(encoding="utf-8"))
        if (
            draft.job_id != job_id
            or draft.phase is not JobPhase.DRAFT
            or draft.module_id.value != task["module_id"]
        ):
            raise ValueError("persisted draft identity is invalid")
        self._validate_draft_paths(job_id, task_dir, draft)
        expected_result = resolve_contained_file(
            Path(draft.output_dir) / "result.json",
            task_dir,
            "draft result file",
            reject_link=True,
        )
        if Path(str(task["result_path"])).resolve() != expected_result:
            raise ValueError("persisted result path does not match draft output")
        result = ModuleResult.model_validate_json(expected_result.read_text(encoding="utf-8"))
        if result.job_id != job_id or result.module_id is not draft.module_id:
            raise ValueError("persisted draft result identity or status is invalid")
        pending = self._prepare_pending_result(job_id, draft, result)
        if pending is None or not pending.confirmations:
            raise ValueError("persisted waiting task has no recoverable confirmations")
        records = self.confirmation_repository.list_for_job(job_id)
        canonical = {
            item.confirmation_id: item.model_dump(mode="json")
            for item in (
                ConfirmationPrompt.model_validate(record["original_prompt"]) for record in records
            )
        }
        result_prompts = {
            item.confirmation_id: item.model_dump(mode="json") for item in pending.confirmations
        }
        if canonical != result_prompts:
            raise ValueError("persisted canonical prompts do not match draft result")
        machine = TaskStateMachine()
        machine.transition(TaskLifecycleState.RUNNING_DRAFT)
        machine.transition(TaskLifecycleState.WAITING_CONFIRMATION)
        self._states[job_id] = machine
        self._jobs[job_id] = draft
        self._pending_confirmation_results[job_id] = pending
        _LOG.info("waiting confirmation recovered job=%s", job_id)

    def _prepare_pending_result(
        self,
        job_id: str,
        job: JobRequest,
        result: ModuleResult,
    ) -> ModuleResult | None:
        if result.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            return None
        prompts = list(result.confirmations)
        if self.monthly_rollup_service is not None:
            adjusted: list[ConfirmationPrompt] = []
            for prompt in prompts:
                if prompt.learning is None:
                    adjusted.append(prompt)
                    continue
                preference = self.monthly_rollup_service.learning.preference(
                    job.module_id.value, prompt.learning
                )
                adjusted.append(
                    prompt
                    if preference is None
                    else prompt.model_copy(
                        update={"suggested_value": preference.candidate_label}
                    )
                )
            prompts = adjusted
        if result.service_requests:
            if self.service_orchestrator is None:
                raise RuntimeError("module requested shared services but none are configured")
            prompts.extend(self._service_consent_prompts(job_id, job, result.service_requests))
        if not prompts and not result.service_requests:
            return None
        identifiers = [prompt.confirmation_id for prompt in prompts]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("module and service confirmation IDs must be unique")
        if not prompts:
            return result
        payload = result.model_dump(mode="python")
        payload["status"] = TaskStatus.NEEDS_CONFIRMATION
        payload["confirmations"] = prompts
        summary = result.summary.model_dump(mode="python")
        summary["confirmation_count"] = len(prompts)
        payload["summary"] = summary
        return ModuleResult.model_validate(payload)

    def _service_consent_prompts(
        self,
        job_id: str,
        job: JobRequest,
        requests: list[ServiceRequest],
    ) -> list[ConfirmationPrompt]:
        del job_id, job, requests
        # v1.3 obtains policy from the global default.  After-sales obtains its
        # exceptional per-task decision before task creation, never as a
        # confirmation item.  Redaction and consent auditing remain mandatory.
        return []

    def _load_draft_result(
        self,
        job_id: str,
        task_dir: Path,
        draft: JobRequest,
    ) -> ModuleResult:
        result_path = resolve_contained_file(
            Path(draft.output_dir) / "result.json",
            task_dir,
            "draft result file",
            reject_link=True,
        )
        result = ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        if result.job_id != job_id or result.module_id is not draft.module_id:
            raise ValueError("draft result identity does not match task")
        return result

    def _service_consent_map(
        self,
        job_id: str,
        bundle: ConfirmationBundle,
        requests: list[ServiceRequest],
    ) -> dict[str, bool]:
        del bundle
        default_allowed = bool(
            self.settings and self.settings.get("ai_network_enabled", "false") == "true"
        )
        allowed = default_allowed or job_id in self._preauthorized_ai
        decisions: dict[str, bool] = {}
        for request in requests:
            if request.service != "ai":
                continue
            decisions[request.request_id] = allowed
        return decisions

    def _ai_authorization_source(self, job_id: str) -> str:
        if self.settings and self.settings.get("ai_network_enabled", "false") == "true":
            return "global_default_allow"
        if job_id in self._preauthorized_ai:
            return "after_sales_task_allow"
        return "global_default_deny"

    def _auto_finalize_services(self, job_id: str) -> None:
        task_dir = resolve_contained_directory(
            self.paths.tasks / job_id,
            self.paths.tasks,
            "service task directory",
            reject_link=True,
        )
        bundle_path = resolve_contained_target(
            task_dir / "confirmation.json",
            task_dir,
            "automatic confirmation file",
            reject_link=True,
        )
        bundle = ConfirmationBundle(job_id=job_id, answers=[])
        _atomic_write_text(bundle_path, bundle.model_dump_json(indent=2))
        self._begin_finalize(job_id, bundle_path, validate_answers=False)

    @staticmethod
    def _error_message(error: Exception) -> str:
        return f"task orchestration failed: {type(error).__name__}: {error}"
