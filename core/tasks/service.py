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
from core.contracts.result import ConfirmationPrompt, ModuleResult, SourceRef
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
from core.tasks.job_builder import build_draft_job
from core.tasks.models import InvalidTaskTransition, TaskLifecycleState, TaskStateMachine
from core.tasks.snapshots import remove_snapshots, snapshot_inputs

if TYPE_CHECKING:
    from core.services.orchestrator import ServiceOrchestrator

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{6,64}$")
_TERMINAL_MARKER = ".terminal-pending.json"
_SERVICE_CONSENT_PREFIX = "service-consent:"
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


class TaskService(QObject):
    progress = Signal(str, object)
    finished = Signal(object)
    needs_confirmation = Signal(str, object)
    failed = Signal(str, str)
    orchestration_error = Signal(str, str)
    status_changed = Signal(str, str)

    def __init__(
        self,
        paths: AppPaths,
        registry: ModuleRegistry,
        task_repository: TaskRepository,
        confirmation_repository: ConfirmationRepository,
        runner_factory: Callable[[], ModuleProcessRunner] = ModuleProcessRunner,
        job_id_factory: Callable[[], str] = _new_job_id,
        service_orchestrator: "ServiceOrchestrator | None" = None,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.task_repository = task_repository
        self.confirmation_repository = confirmation_repository
        self.runner_factory = runner_factory
        self.job_id_factory = job_id_factory
        self.service_orchestrator = service_orchestrator
        self.runners: dict[str, ModuleProcessRunner] = {}
        self._states: dict[str, TaskStateMachine] = {}
        self._jobs: dict[str, JobRequest] = {}
        self._failed_signals: set[str] = set()
        self._cancellation_pending: set[str] = set()
        self._pending_confirmation_results: dict[str, ModuleResult] = {}
        self._shutdown = False
        self._shutdown_result = True
        self._blocked_callbacks: set[str] = set()
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

    def create_and_start(self, module_id: ModuleId, inputs: list[Path]) -> str:
        timestamp = datetime.now().astimezone()
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
            )
        except Exception:
            shutil.rmtree(task_dir)
            raise

        self._states[job_id] = TaskStateMachine()
        runner: ModuleProcessRunner | None = None
        try:
            module = self.registry.get(module_id)
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
            job = build_draft_job(
                job_id,
                module_id,
                [snapshot.copy for snapshot in snapshots],
                task_dir,
            )
            job_path = task_dir / "job-draft.json"
            job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
            self._jobs[job_id] = job
            self._persist_transition(job_id, TaskLifecycleState.RUNNING_DRAFT)
            runner = self.runner_factory()
            self.runners[job_id] = runner
            self._connect_runner(job_id, runner)
            runner.start(module, job_path)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
        return job_id

    def finalize(self, job_id: str, bundle_path: Path) -> None:
        self._begin_finalize(job_id, bundle_path, validate_answers=True)

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
        service_response_file: str | None = None
        ai_consent: dict[str, bool] = {}
        if draft_result.service_requests:
            if self.service_orchestrator is None:
                raise RuntimeError("module requested shared services but none are configured")
            ai_consent = self._service_consent_map(bundle, draft_result.service_requests)
            response_path = self.service_orchestrator.resolve(
                task_id=job_id,
                module_id=trusted_draft.module_id.value,
                allowed_namespaces=set(trusted_draft.allowed_knowledge_scopes),
                requests=draft_result.service_requests,
                ai_consent=ai_consent,
                task_dir=task_dir,
            )
            service_response_file = str(response_path)
        final_payload = trusted_draft.model_dump(mode="python")
        final_payload.update(
            phase=JobPhase.FINALIZE,
            parent_job_id=job_id,
            confirmation_file=str(frozen_bundle_path),
            output_dir=str(final_output_dir),
            service_response_file=service_response_file,
            ai_enabled=any(ai_consent.values()),
        )
        final_job = JobRequest.model_validate(final_payload)
        final_path = task_dir / "job-finalize.json"
        _atomic_write_text(frozen_bundle_path, bundle.model_dump_json(indent=2))
        _atomic_write_text(final_path, final_job.model_dump_json(indent=2))

        self._persist_transition(job_id, TaskLifecycleState.RUNNING_FINALIZE)
        self._pending_confirmation_results.pop(job_id, None)
        self._jobs[job_id] = final_job
        runner: ModuleProcessRunner | None = None
        try:
            runner = self.runner_factory()
            self.runners[job_id] = runner
            self._connect_runner(job_id, runner)
            runner.start(self.registry.get(trusted_draft.module_id), final_path)
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
        if draft.ai_enabled:
            raise ValueError("job-draft ai_enabled must remain false")
        if draft.allowed_knowledge_scopes != ["shared", draft.module_id.value]:
            raise ValueError("job-draft knowledge scopes are not canonical")
        if any(
            value is not None
            for value in (
                draft.module_config_file,
                draft.service_response_file,
                draft.parent_job_id,
                draft.confirmation_file,
            )
        ):
            raise ValueError("job-draft finalize-only or config fields must be empty")

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
                target = TaskLifecycleState(result.status.value)
                if result.status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
                    self.task_repository.replace_outputs(job_id, result.outputs)
                self._persist_transition(job_id, target, result_path=result_path)
                _LOG.info("task terminal job=%s status=%s", job_id, target.value)
                self.finished.emit(result)
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
        if self.service_orchestrator is None:
            return []
        prompts: list[ConfirmationPrompt] = []
        for request in requests:
            if request.service != "ai" or not request.requires_user_consent:
                continue
            preview = self.service_orchestrator.preview_ai(
                job_id,
                job.module_id.value,
                request,
            )
            preview_text = json.dumps(preview.payload, ensure_ascii=False, sort_keys=True)
            categories = "、".join(preview.categories) or "无敏感类别"
            prompts.append(
                ConfirmationPrompt(
                    confirmation_id=f"{_SERVICE_CONSENT_PREFIX}{request.request_id}",
                    field=f"AI联网授权：{request.purpose}",
                    reason=(
                        f"发送内容已脱敏；识别类别：{categories}；"
                        f"脱敏预览：{preview_text[:800]}"
                    ),
                    suggested_value="拒绝",
                    options=["允许", "拒绝"],
                    confidence=1.0,
                    blocking=True,
                    batch_applicable=False,
                    rememberable=False,
                    source=SourceRef(source_file=job.input_files[0]),
                )
            )
        return prompts

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

    @staticmethod
    def _service_consent_map(
        bundle: ConfirmationBundle,
        requests: list[ServiceRequest],
    ) -> dict[str, bool]:
        supplied = {answer.confirmation_id: answer.value for answer in bundle.answers}
        decisions: dict[str, bool] = {}
        for request in requests:
            if request.service != "ai":
                continue
            if not request.requires_user_consent:
                decisions[request.request_id] = True
                continue
            key = f"{_SERVICE_CONSENT_PREFIX}{request.request_id}"
            value = supplied.get(key)
            if isinstance(value, bool):
                decisions[request.request_id] = value
            else:
                decisions[request.request_id] = str(value).strip().lower() in {
                    "1",
                    "allow",
                    "allowed",
                    "true",
                    "yes",
                    "允许",
                    "同意",
                }
        return decisions

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
