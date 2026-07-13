import itertools
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry
from core.platform.paths import AppPaths
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.job_builder import build_draft_job
from core.tasks.models import TaskLifecycleState, TaskStateMachine
from core.tasks.snapshots import snapshot_inputs


class TaskService(QObject):
    progress = Signal(str, object)
    finished = Signal(object)
    needs_confirmation = Signal(str, object)
    failed = Signal(str, str)

    _counter = itertools.count(1)

    def __init__(
        self,
        paths: AppPaths,
        registry: ModuleRegistry,
        task_repository: TaskRepository,
        confirmation_repository: ConfirmationRepository,
        runner_factory: Callable[[], ModuleProcessRunner] = ModuleProcessRunner,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.task_repository = task_repository
        self.confirmation_repository = confirmation_repository
        self.runner_factory = runner_factory
        self.runners: dict[str, ModuleProcessRunner] = {}
        self._states: dict[str, TaskStateMachine] = {}
        self._jobs: dict[str, JobRequest] = {}
        self._failed_signals: set[str] = set()

    def create_and_start(self, module_id: ModuleId, inputs: list[Path]) -> str:
        timestamp = datetime.now().astimezone()
        job_id = f"{timestamp:%Y%m%d-%H%M%S}-{next(self._counter):03d}"
        try:
            self.task_repository.create(
                job_id,
                module_id.value,
                TaskLifecycleState.CREATED.value,
                timestamp.isoformat(),
            )
        except Exception:
            return job_id

        self._states[job_id] = TaskStateMachine()
        runner: ModuleProcessRunner | None = None
        try:
            self.paths.ensure()
            module = self.registry.get(module_id)
            task_dir = self.paths.tasks / job_id
            snapshots = snapshot_inputs(
                inputs,
                task_dir,
                supported_extensions=module.manifest.supported_extensions,
            )
            for snapshot in snapshots:
                self.task_repository.add_file(
                    job_id,
                    str(snapshot.source),
                    str(snapshot.copy),
                    snapshot.fingerprint,
                    "snapshotted",
                )
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
            self._connect_runner(job_id, runner)
            self.runners[job_id] = runner
            runner.start(module, job_path)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
        return job_id

    def _connect_runner(self, job_id: str, runner: ModuleProcessRunner) -> None:
        runner.progress.connect(
            lambda event, active=runner: self._forward_progress(job_id, event, active)
        )
        runner.completed.connect(
            lambda result, active=runner: self._complete(job_id, result, active)
        )
        runner.failed.connect(
            lambda message, active=runner: self._record_failure(
                job_id, str(message), active
            )
        )
        runner.cancelled.connect(lambda active=runner: self._cancelled(job_id, active))

    def _forward_progress(
        self, job_id: str, event: object, runner: ModuleProcessRunner
    ) -> None:
        if self.runners.get(job_id) is runner:
            self.progress.emit(job_id, event)

    def _complete(
        self, job_id: str, result: ModuleResult, runner: ModuleProcessRunner
    ) -> None:
        if self.runners.get(job_id) is not runner:
            return
        try:
            job = self._jobs[job_id]
            result_path = str((Path(job.output_dir) / "result.json").resolve())
            if result.status is TaskStatus.NEEDS_CONFIRMATION:
                self.confirmation_repository.save_prompts(job_id, result.confirmations)
                self._persist_transition(
                    job_id,
                    TaskLifecycleState.WAITING_CONFIRMATION,
                    result_path=result_path,
                )
                self.needs_confirmation.emit(job_id, result)
            else:
                target = TaskLifecycleState(result.status.value)
                if result.status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
                    self.task_repository.replace_outputs(job_id, result.outputs)
                self._persist_transition(job_id, target, result_path=result_path)
                self.finished.emit(result)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
            return
        self._cleanup_runner(job_id, runner)

    def _cancelled(self, job_id: str, runner: ModuleProcessRunner) -> None:
        if self.runners.get(job_id) is not runner:
            return
        try:
            self._persist_transition(job_id, TaskLifecycleState.CANCELLED)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
            return
        self._cleanup_runner(job_id, runner)

    def _record_failure(
        self,
        job_id: str,
        message: str,
        runner: ModuleProcessRunner | None = None,
    ) -> None:
        if runner is not None and self.runners.get(job_id) is not runner:
            return
        if job_id in self._failed_signals:
            self._cleanup_runner(job_id, runner)
            return
        try:
            self._persist_transition(job_id, TaskLifecycleState.FAILED, error=message)
        except Exception as exc:
            message = f"{message}; failure persistence error: {exc}"
        self._failed_signals.add(job_id)
        self.failed.emit(job_id, message)
        self._cleanup_runner(job_id, runner)

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

    def _cleanup_runner(
        self, job_id: str, runner: ModuleProcessRunner | None = None
    ) -> None:
        active = self.runners.get(job_id)
        if runner is not None and active is not runner:
            return
        removed = self.runners.pop(job_id, None)
        if removed is not None:
            removed.deleteLater()

    @staticmethod
    def _error_message(error: Exception) -> str:
        return f"task orchestration failed: {type(error).__name__}: {error}"
