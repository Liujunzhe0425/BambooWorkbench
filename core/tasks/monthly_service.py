"""Coordinates deterministic module rollups and atomic official-slot commits."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal

from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.monthly import (
    MonthlyRollupRequest,
    MonthlyRollupResult,
    RollupSnapshotRef,
)
from core.contracts.result import ConfirmationPrompt, ModuleResult, OutputArtifact
from core.knowledge.learning import LearningEvidenceRepository
from core.modules.monthly_runner import MonthlyRollupRunner
from core.modules.registry import ModuleRegistry, RegisteredModule
from core.platform.installation import inspect_installation
from core.platform.path_safety import resolve_contained_file
from core.platform.paths import AppPaths
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.monthly import MonthlyRepository
from core.storage.repositories.output_roots import OutputRootRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.output_manifest import (
    OutputManifestMetadata,
    mark_output_manifest_superseded,
)
from core.tasks.output_publisher import publish_outputs

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(slots=True)
class _RollupContext:
    job_id: str
    module: RegisteredModule
    original_result: ModuleResult
    transaction_id: str
    candidate_snapshot: dict[str, object]
    old_job_id: str | None
    target_months: list[int]
    pending_months: list[int]
    operation: str = "replace"
    requests: dict[int, MonthlyRollupRequest] = field(default_factory=dict)
    results: dict[int, MonthlyRollupResult] = field(default_factory=dict)
    published_directories: list[Path] = field(default_factory=list)
    prior_manifests: set[Path] = field(default_factory=set)


class MonthlyRollupService(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str, bool)
    progress = Signal(str, int, int)
    detail_progress = Signal(str, object)
    governance_completed = Signal(str, int, int)
    governance_failed = Signal(str)

    def __init__(
        self,
        paths: AppPaths,
        registry: ModuleRegistry,
        tasks: TaskRepository,
        confirmations: ConfirmationRepository,
        monthly: MonthlyRepository,
        learning: LearningEvidenceRepository,
        output_roots: OutputRootRepository,
        runner_factory: Callable[[], MonthlyRollupRunner] = MonthlyRollupRunner,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.tasks = tasks
        self.confirmations = confirmations
        self.monthly = monthly
        self.learning = learning
        self.output_roots = output_roots
        self.runner_factory = runner_factory
        self._contexts: dict[str, _RollupContext] = {}
        self._runners: dict[str, MonthlyRollupRunner] = {}
        self._reconcile_interrupted()

    def start(self, job_id: str, result: ModuleResult) -> None:
        if job_id in self._contexts:
            raise RuntimeError("monthly rollup is already active for this task")
        task = self.tasks.get(job_id)
        module = self.registry.get(result.module_id)
        if module.manifest.monthly_rollup is None:
            raise ValueError("module does not declare monthly_rollup")
        year = _required_int(task, "period_year")
        month = _required_int(task, "period_month")
        snapshot_artifact = result.monthly_snapshot
        if snapshot_artifact is None:
            raise ValueError("finalize result did not provide a monthly snapshot")
        source = resolve_contained_file(
            Path(snapshot_artifact.path),
            self.paths.tasks / job_id,
            "monthly snapshot",
            reject_link=True,
        )
        immutable = self.paths.tasks / job_id / "monthly-snapshot.json"
        if not immutable.exists():
            _atomic_copy(source, immutable)
            immutable.chmod(0o444)
        digest = _sha256(immutable)
        snapshot = self.monthly.get_snapshot_for_job(job_id)
        if snapshot is None:
            snapshot_id = self.monthly.register_snapshot(
                module_id=result.module_id.value,
                year=year,
                month=month,
                job_id=job_id,
                contract_version=snapshot_artifact.schema_version,
                snapshot_format=snapshot_artifact.snapshot_format,
                path=immutable,
                size=immutable.stat().st_size,
                sha256=digest,
            )
            snapshot = self.monthly.get_snapshot_for_job(job_id)
            assert snapshot is not None and snapshot["snapshot_id"] == snapshot_id
        elif snapshot["sha256"] != digest:
            raise ValueError("registered monthly snapshot no longer matches its immutable copy")
        self._stage_learning(task, result.module_id.value)
        official = self.monthly.list_year(result.module_id.value, year)
        affected = [month, *(int(slot["month"]) for slot in official if slot["month"] > month)]
        old_slot = self.monthly.get_slot(result.module_id.value, year, month)
        transaction_id = self.monthly.begin_transaction(
            module_id=result.module_id.value,
            year=year,
            candidate_month=month,
            candidate_job_id=job_id,
            affected_months=affected,
        )
        self.monthly.set_transaction_state(transaction_id, "rendering")
        context = _RollupContext(
            job_id=job_id,
            module=module,
            original_result=result,
            transaction_id=transaction_id,
            candidate_snapshot=snapshot,
            old_job_id=None if old_slot is None else str(old_slot["official_job_id"]),
            target_months=affected,
            pending_months=list(affected),
        )
        self._start_context(context)

    def shutdown(self) -> bool:
        ok = True
        for runner in tuple(self._runners.values()):
            ok = runner.shutdown() and ok
        self._runners.clear()
        self._contexts.clear()
        return ok

    def remove_official(self, module_id: str, year: int, month: int) -> None:
        slot = self.monthly.get_slot(module_id, year, month)
        if slot is None:
            raise ValueError("该月份没有可移除的正式结果")
        job_id = str(slot["official_job_id"])
        later = [
            int(item["month"])
            for item in self.monthly.list_year(module_id, year)
            if int(item["month"]) > month
        ]
        if not later:
            self.monthly.remove_official_without_later(module_id, year, month, job_id)
            for manifest in self._task_output_manifests(job_id):
                mark_output_manifest_superseded(manifest, "official-task-removed")
            self.governance_completed.emit(module_id, year, month)
            return
        task_dir = self.paths.tasks / job_id
        final_result = resolve_contained_file(
            task_dir / "output-final" / "result.json",
            task_dir,
            "official task result",
            reject_link=True,
        )
        result = ModuleResult.model_validate_json(final_result.read_text(encoding="utf-8"))
        module = self.registry.get(result.module_id)
        snapshot = self.monthly.get_snapshot_for_job(job_id)
        if snapshot is None:
            raise ValueError("正式任务缺少内部月度快照")
        transaction_id = self.monthly.begin_transaction(
            module_id=module_id,
            year=year,
            candidate_month=month,
            candidate_job_id=job_id,
            affected_months=later,
        )
        self.monthly.set_transaction_state(transaction_id, "rendering")
        context = _RollupContext(
            job_id=job_id,
            module=module,
            original_result=result,
            transaction_id=transaction_id,
            candidate_snapshot=snapshot,
            old_job_id=job_id,
            target_months=later,
            pending_months=list(later),
            operation="remove",
        )
        self._start_context(context)

    def regenerate_official(self, module_id: str, year: int, month: int) -> None:
        slot = self.monthly.get_slot(module_id, year, month)
        if slot is None:
            raise ValueError("该月份没有可重新生成的正式结果")
        job_id = str(slot["official_job_id"])
        task_dir = self.paths.tasks / job_id
        final_result = resolve_contained_file(
            task_dir / "output-final" / "result.json",
            task_dir,
            "official task result",
            reject_link=True,
        )
        result = ModuleResult.model_validate_json(final_result.read_text(encoding="utf-8"))
        snapshot = self.monthly.get_snapshot_for_job(job_id)
        if snapshot is None:
            raise ValueError("正式任务缺少内部月度快照")
        affected = [
            int(item["month"])
            for item in self.monthly.list_year(module_id, year)
            if int(item["month"]) >= month
        ]
        transaction_id = self.monthly.begin_transaction(
            module_id=module_id,
            year=year,
            candidate_month=month,
            candidate_job_id=job_id,
            affected_months=affected,
        )
        self.monthly.set_transaction_state(transaction_id, "rendering")
        context = _RollupContext(
            job_id=job_id,
            module=self.registry.get(result.module_id),
            original_result=result,
            transaction_id=transaction_id,
            candidate_snapshot=snapshot,
            old_job_id=job_id,
            target_months=affected,
            pending_months=list(affected),
            operation="regenerate",
        )
        self._start_context(context)

    def _reconcile_interrupted(self) -> None:
        for transaction in self.monthly.list_interrupted():
            transaction_id = str(transaction["transaction_id"])
            job_id = str(transaction["candidate_job_id"])
            self.monthly.set_transaction_state(
                transaction_id,
                "failed",
                error_code="application_interrupted",
                error_message="application stopped before the rollup transaction committed",
            )
            if transaction["old_job_id"] == transaction["candidate_job_id"]:
                continue
            target = "replacement_candidate" if transaction["old_job_id"] else "failed"
            self.tasks.update_status(
                job_id,
                target,
                error="累计生成被应用退出中断；正式月度结果未改变，可重新尝试。",
            )

    def _run_next(self, context: _RollupContext) -> None:
        if not context.pending_months:
            self._commit(context)
            return
        target_month = context.pending_months[0]
        request = self._build_request(context, target_month)
        context.requests[target_month] = request
        task_dir = self.paths.tasks / context.job_id
        request_dir = task_dir / "rollup" / context.transaction_id / f"{target_month:02d}"
        request_dir.mkdir(parents=True, exist_ok=True)
        request_path = request_dir / "rollup-request.json"
        _atomic_write(request_path, request.model_dump_json(indent=2))
        runner = self.runner_factory()
        self._runners[context.job_id] = runner
        runner.progress.connect(
            lambda event: self.detail_progress.emit(context.job_id, event)
        )
        runner.completed.connect(
            lambda result, active=runner, month=target_month: self._rollup_completed(
                context.job_id, month, result, active
            )
        )
        runner.failed.connect(
            lambda message, active=runner, month=target_month: self._rollup_failed(
                context.job_id, month, str(message), active
            )
        )
        runner.cancelled.connect(
            lambda active=runner, month=target_month: self._rollup_failed(
                context.job_id, month, "monthly rollup cancelled", active
            )
        )
        runner.start(context.module, request_path)

    def _start_context(self, context: _RollupContext) -> None:
        self._contexts[context.job_id] = context
        try:
            self._run_next(context)
        except Exception as error:
            target_month = context.pending_months[0]
            self._fail_context(context, target_month, str(error))

    def _build_request(
        self, context: _RollupContext, target_month: int
    ) -> MonthlyRollupRequest:
        task = self.tasks.get(context.job_id)
        year = _required_int(task, "period_year")
        official = self.monthly.list_official_snapshots(
            context.module.manifest.module_id.value, year, target_month
        )
        by_month = {int(snapshot["month"]): snapshot for snapshot in official}
        candidate_month = int(context.candidate_snapshot["month"])
        if context.operation == "remove":
            by_month.pop(candidate_month, None)
        else:
            by_month[candidate_month] = context.candidate_snapshot
        request_root = (
            self.paths.tasks
            / context.job_id
            / "rollup"
            / context.transaction_id
            / f"{target_month:02d}"
        )
        snapshot_root = request_root / "snapshots"
        output_dir = request_root / "output"
        snapshot_root.mkdir(parents=True, exist_ok=False)
        output_dir.mkdir(parents=True, exist_ok=False)
        snapshots: list[RollupSnapshotRef] = []
        for month, snapshot in sorted(by_month.items()):
            if month > target_month:
                continue
            source = Path(str(snapshot["path"]))
            destination = snapshot_root / (
                f"{month:02d}-{str(snapshot['snapshot_id'])}.json"
            )
            _atomic_copy(source, destination)
            destination.chmod(0o444)
            if (
                destination.stat().st_size != int(snapshot["size"])
                or _sha256(destination) != str(snapshot["sha256"])
            ):
                raise ValueError("authorized snapshot copy failed integrity validation")
            snapshots.append(
                RollupSnapshotRef(
                    snapshot_id=str(snapshot["snapshot_id"]),
                    job_id=str(snapshot["job_id"]),
                    module_id=context.module.manifest.module_id,
                    year=year,
                    month=month,
                    path=str(destination.resolve()),
                    size=int(snapshot["size"]),
                    sha256=str(snapshot["sha256"]),
                )
            )
        return MonthlyRollupRequest(
            schema_version="1.0",
            transaction_id=context.transaction_id,
            module_id=context.module.manifest.module_id,
            module_version=context.module.manifest.module_version,
            year=year,
            target_month=target_month,
            snapshots=snapshots,
            snapshot_root=str(snapshot_root.resolve()),
            output_dir=str(output_dir.resolve()),
            configuration_identity=self._configuration_identity(
                context, target_month
            ),
            offline_required=True,
        )

    def _rollup_completed(
        self,
        job_id: str,
        target_month: int,
        result: MonthlyRollupResult,
        runner: MonthlyRollupRunner,
    ) -> None:
        if self._runners.get(job_id) is not runner:
            return
        self._runners.pop(job_id, None)
        context = self._contexts[job_id]
        request = context.requests[target_month]
        manifest_digest = _result_digest(result)
        self.monthly.validate_item(
            context.transaction_id,
            target_month,
            staged_path=Path(request.output_dir),
            manifest_sha256=manifest_digest,
        )
        context.results[target_month] = result
        context.pending_months.pop(0)
        self.progress.emit(
            job_id, len(context.results), len(context.target_months)
        )
        try:
            self._run_next(context)
        except Exception as error:
            self._fail_context(context, context.pending_months[0], str(error))

    def _rollup_failed(
        self,
        job_id: str,
        target_month: int,
        message: str,
        runner: MonthlyRollupRunner,
    ) -> None:
        if self._runners.get(job_id) is not runner:
            return
        self._runners.pop(job_id, None)
        context = self._contexts.pop(job_id)
        self.monthly.fail_item(
            context.transaction_id,
            target_month,
            "rollup_failed",
            message,
        )
        if context.operation != "replace":
            self.governance_failed.emit(message)
        else:
            self.failed.emit(job_id, message, context.old_job_id is not None)

    def _fail_context(
        self, context: _RollupContext, target_month: int, message: str
    ) -> None:
        self._contexts.pop(context.job_id, None)
        self.monthly.fail_item(
            context.transaction_id,
            target_month,
            "orchestration_failed",
            message,
        )
        if context.operation != "replace":
            self.governance_failed.emit(message)
        else:
            self.failed.emit(
                context.job_id, message, context.old_job_id is not None
            )

    def _commit(self, context: _RollupContext) -> None:
        published_by_job: dict[str, list[OutputArtifact]] = {}
        candidate_display: ModuleResult | None = None
        try:
            now = datetime.now().astimezone().isoformat()
            installation = inspect_installation(self.paths)
            installation_id = (
                installation.instance_id if installation is not None else "development-instance"
            )
            snapshot_by_month: dict[int, str] = {}
            for month in context.target_months:
                target_slot = self.monthly.get_slot(
                    context.module.manifest.module_id.value,
                    _required_int(self.tasks.get(context.job_id), "period_year"),
                    month,
                )
                target_job_id = (
                    context.job_id
                    if context.operation == "replace"
                    and month == int(context.candidate_snapshot["month"])
                    else str(target_slot["official_job_id"])
                )
                target_snapshot = (
                    context.candidate_snapshot
                    if target_job_id == context.job_id
                    else self.monthly.get_snapshot_for_job(target_job_id)
                )
                if target_snapshot is None:
                    raise ValueError("affected official task has no monthly snapshot")
                snapshot_by_month[month] = str(target_snapshot["snapshot_id"])
                target_task = self.tasks.get(target_job_id)
                context.prior_manifests.update(self._task_output_manifests(target_job_id))
                root = self._output_root_for_task(target_task)
                rollup_result = context.results[month]
                template = context.original_result.model_copy(
                    update={"job_id": target_job_id, "outputs": rollup_result.outputs}
                )
                metadata = OutputManifestMetadata(
                    installation_id=installation_id,
                    job_id=target_job_id,
                    task_name=str(target_task["task_name"]),
                    module_id=str(target_task["module_id"]),
                    year=_required_int(target_task, "period_year"),
                    month=_required_int(target_task, "period_month"),
                    created_at=str(target_task["created_at"]),
                    completed_at=now,
                    committed_at=now,
                    snapshot_format=str(target_snapshot["snapshot_format"]),
                    snapshot_sha256=str(target_snapshot["sha256"]),
                    replacement_for_job_id=(
                        context.old_job_id
                        if context.operation == "replace"
                        and target_job_id == context.job_id
                        else None
                    ),
                    transaction_id=context.transaction_id,
                )
                published = publish_outputs(
                    template,
                    task_name=str(target_task["task_name"]),
                    task_dir=self.paths.tasks / context.job_id,
                    task_output_dir=Path(context.requests[month].output_dir),
                    configured_root=str(root),
                    manifest_metadata=metadata,
                    folder_timestamp=datetime.fromisoformat(
                        str(target_task["created_at"])
                    ),
                )
                first_relative = Path(published.outputs[0].path).relative_to(root).parts[0]
                output_directory = root / first_relative
                context.published_directories.append(output_directory)
                published_by_job[target_job_id] = list(published.outputs)
                if context.operation == "replace" and target_job_id == context.job_id:
                    candidate_display = context.original_result.model_copy(
                        update={"outputs": published.outputs}
                    )
            self.monthly.commit(
                context.transaction_id,
                snapshot_by_month=snapshot_by_month,
                outputs_by_job=published_by_job,
                activate_learning_job=(
                    context.job_id if context.operation == "replace" else None
                ),
                revoke_learning_job=(
                    context.old_job_id
                    if context.operation in {"replace", "remove"}
                    else None
                ),
                remove_slot=(
                    (
                        context.module.manifest.module_id.value,
                        _required_int(self.tasks.get(context.job_id), "period_year"),
                        int(context.candidate_snapshot["month"]),
                    )
                    if context.operation == "remove"
                    else None
                ),
            )
            if context.old_job_id is not None:
                context.prior_manifests.update(
                    self._task_output_manifests(context.old_job_id)
                )
            for manifest in context.prior_manifests:
                try:
                    mark_output_manifest_superseded(
                        manifest, context.transaction_id
                    )
                except (OSError, ValueError):
                    continue
        except Exception as error:
            for directory in context.published_directories:
                _remove_created_directory(directory)
            self.monthly.set_transaction_state(
                context.transaction_id,
                "failed",
                error_code="commit_failed",
                error_message=str(error),
            )
            self._contexts.pop(context.job_id, None)
            if context.operation != "replace":
                self.governance_failed.emit(str(error))
            else:
                self.failed.emit(
                    context.job_id, str(error), context.old_job_id is not None
                )
            return
        self._contexts.pop(context.job_id, None)
        if context.operation != "replace":
            self.governance_completed.emit(
                context.module.manifest.module_id.value,
                _required_int(self.tasks.get(context.job_id), "period_year"),
                int(context.candidate_snapshot["month"]),
            )
        else:
            assert candidate_display is not None
            self.completed.emit(context.job_id, candidate_display)

    def _output_root_for_task(self, task: dict[str, object]) -> Path:
        root_id = task.get("output_root_id")
        if isinstance(root_id, int):
            return Path(str(self.output_roots.get(root_id)["path"]))
        return Path(str(self.output_roots.current()["path"]))

    def _task_output_manifests(self, job_id: str) -> set[Path]:
        manifests: set[Path] = set()
        for record in self.tasks.list_outputs(job_id):
            candidate = Path(str(record["path"])).parent
            for parent in (candidate, *candidate.parents[:3]):
                manifest = parent / ".bamboo-task.json"
                if manifest.is_file():
                    manifests.add(manifest)
                    break
        return manifests

    def _configuration_identity(
        self, context: _RollupContext, target_month: int
    ) -> dict[str, str] | None:
        candidate_month = int(context.candidate_snapshot["month"])
        if context.operation == "replace" and target_month == candidate_month:
            job_id = context.job_id
        else:
            slot = self.monthly.get_slot(
                context.module.manifest.module_id.value,
                _required_int(self.tasks.get(context.job_id), "period_year"),
                target_month,
            )
            job_id = context.job_id if slot is None else str(slot["official_job_id"])
        task_dir = self.paths.tasks / job_id
        final_job_path = task_dir / "job-finalize.json"
        if not final_job_path.is_file():
            return None
        job = json.loads(final_job_path.read_text(encoding="utf-8"))
        config_path = job.get("module_config_file")
        if not isinstance(config_path, str):
            return None
        config_file = resolve_contained_file(
            Path(config_path), task_dir, "rollup module configuration", reject_link=True
        )
        payload = json.loads(config_file.read_text(encoding="utf-8"))
        identity = payload.get("rule_selection")
        if (
            not isinstance(identity, dict)
            or set(identity) != {"version", "sha256"}
            or not all(isinstance(value, str) for value in identity.values())
        ):
            return None
        return {"version": identity["version"], "sha256": identity["sha256"]}

    def _stage_learning(self, task: dict[str, object], module_id: str) -> None:
        if not bool(task["learning_enabled"]) or self.learning.has_staged_for_job(
            str(task["job_id"])
        ):
            return
        for record in self.confirmations.list_for_job(str(task["job_id"])):
            if record["answer"] is None:
                continue
            prompt = ConfirmationPrompt.model_validate(record["original_prompt"])
            if prompt.learning is None or not prompt.learning.preference_adjustable:
                continue
            answer = ConfirmationAnswer.model_validate(record["answer"])
            candidate_id = _candidate_id(prompt, answer.value)
            if candidate_id is None:
                continue
            self.learning.stage(
                job_id=str(task["job_id"]),
                module_id=module_id,
                year=_required_int(task, "period_year"),
                month=_required_int(task, "period_month"),
                confirmation_id=prompt.confirmation_id,
                descriptor=prompt.learning,
                candidate_id=candidate_id,
            )


def _candidate_id(prompt: ConfirmationPrompt, value: object) -> str | None:
    assert prompt.learning is not None
    text = str(value)
    for candidate in prompt.learning.candidates:
        if text in {candidate.candidate_id, candidate.label}:
            return candidate.candidate_id
    return None


def _required_int(record: dict[str, object], key: str) -> int:
    value = record.get(key)
    if not isinstance(value, int):
        raise ValueError(f"task is missing {key}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result_digest(result: MonthlyRollupResult) -> str:
    payload = result.model_dump_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_copy(source: Path, destination: Path) -> None:
    descriptor, name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    os.close(descriptor)
    temporary = Path(name)
    try:
        shutil.copyfile(source, temporary)
        with temporary.open("rb+") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_write(path: Path, content: str) -> None:
    descriptor, name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", text=True
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _remove_created_directory(directory: Path) -> None:
    try:
        resolved = directory.resolve(strict=True)
        for item in resolved.rglob("*"):
            if item.is_file():
                item.chmod(0o666)
        shutil.rmtree(resolved)
    except OSError:
        return
