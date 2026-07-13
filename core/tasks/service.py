import os
import re
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Signal

from core.contracts.confirmation import ConfirmationAnswer, ConfirmationBundle
from core.contracts.enums import JobPhase, ModuleId, TaskStatus
from core.contracts.job import JobRequest
from core.contracts.result import ConfirmationPrompt, ModuleResult
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

_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9-]{6,64}$")


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

    def __init__(
        self,
        paths: AppPaths,
        registry: ModuleRegistry,
        task_repository: TaskRepository,
        confirmation_repository: ConfirmationRepository,
        runner_factory: Callable[[], ModuleProcessRunner] = ModuleProcessRunner,
        job_id_factory: Callable[[], str] = _new_job_id,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.task_repository = task_repository
        self.confirmation_repository = confirmation_repository
        self.runner_factory = runner_factory
        self.job_id_factory = job_id_factory
        self.runners: dict[str, ModuleProcessRunner] = {}
        self._states: dict[str, TaskStateMachine] = {}
        self._jobs: dict[str, JobRequest] = {}
        self._failed_signals: set[str] = set()

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
            raise InvalidTaskTransition(
                "persisted task state is not waiting_confirmation"
            )

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
        self._validate_stored_answers(job_id, bundle)

        draft_path = resolve_contained_file(
            task_dir / "job-draft.json",
            task_dir,
            "draft job file",
            reject_link=True,
        )
        draft = JobRequest.model_validate_json(draft_path.read_text(encoding="utf-8"))
        if draft.job_id != job_id or draft.phase is not JobPhase.DRAFT:
            raise ValueError("job-draft identity or phase does not match task")
        if draft.module_id.value != task["module_id"]:
            raise ValueError("job-draft module_id does not match persisted task")
        self._validate_draft_paths(job_id, task_dir, draft)

        final_output_dir = resolve_contained_target(
            task_dir / "output-final",
            task_dir,
            "final output",
            reject_link=True,
        )
        final_payload = draft.model_dump(mode="python")
        final_payload.update(
            phase=JobPhase.FINALIZE,
            parent_job_id=job_id,
            confirmation_file=str(resolved_bundle_path),
            output_dir=str(final_output_dir),
        )
        final_job = JobRequest.model_validate(final_payload)
        final_path = task_dir / "job-finalize.json"
        _atomic_write_text(final_path, final_job.model_dump_json(indent=2))

        self._persist_transition(job_id, TaskLifecycleState.RUNNING_FINALIZE)
        self._jobs[job_id] = final_job
        runner: ModuleProcessRunner | None = None
        try:
            runner = self.runner_factory()
            self.runners[job_id] = runner
            self._connect_runner(job_id, runner)
            runner.start(self.registry.get(draft.module_id), final_path)
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)

    def _validate_draft_paths(
        self, job_id: str, task_dir: Path, draft: JobRequest
    ) -> None:
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

    def _validate_stored_answers(
        self, job_id: str, bundle: ConfirmationBundle
    ) -> None:
        records = self.confirmation_repository.list_for_job(job_id)
        if not records:
            raise ValueError("stored answered state has no canonical prompts")
        prompts = {
            prompt.confirmation_id: prompt
            for prompt in (
                ConfirmationPrompt.model_validate(record["original_prompt"])
                for record in records
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
            confirmation_id
            for confirmation_id, prompt in prompts.items()
            if prompt.blocking
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
                task_terminal = False
            else:
                target = TaskLifecycleState(result.status.value)
                if result.status in {TaskStatus.SUCCESS, TaskStatus.PARTIAL_SUCCESS}:
                    self.task_repository.replace_outputs(job_id, result.outputs)
                self._persist_transition(job_id, target, result_path=result_path)
                self.finished.emit(result)
                task_terminal = True
        except Exception as exc:
            self._record_failure(job_id, self._error_message(exc), runner)
            return
        self._cleanup_runner(job_id, runner, task_terminal=task_terminal)

    def _cancelled(self, job_id: str, runner: ModuleProcessRunner) -> None:
        if self.runners.get(job_id) is not runner:
            return
        try:
            self._persist_transition(job_id, TaskLifecycleState.CANCELLED)
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
        if runner is not None and self.runners.get(job_id) is not runner:
            return
        if job_id in self._failed_signals:
            self._cleanup_runner(job_id, runner, task_terminal=True)
            return
        try:
            self._persist_transition(job_id, TaskLifecycleState.FAILED, error=message)
        except Exception as exc:
            message = f"{message}; failure persistence error: {exc}"
        self._failed_signals.add(job_id)
        self.failed.emit(job_id, message)
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
        if removed is not None:
            removed.deleteLater()
        if task_terminal:
            self._states.pop(job_id, None)
            self._jobs.pop(job_id, None)
            self._failed_signals.discard(job_id)

    @staticmethod
    def _error_message(error: Exception) -> str:
        return f"task orchestration failed: {type(error).__name__}: {error}"
