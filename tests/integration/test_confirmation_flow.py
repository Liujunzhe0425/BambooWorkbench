from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.confirmations.service import ConfirmationService
from core.contracts.confirmation import ConfirmationAnswer, ConfirmationBundle
from core.contracts.enums import JobPhase, ModuleId
from core.contracts.job import JobRequest
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.models import InvalidTaskTransition
from core.tasks.service import TaskService


def _task_service(app_services: dict[str, object], **kwargs: object) -> TaskService:
    return TaskService(
        paths=app_services["paths"],
        registry=app_services["registry"],
        task_repository=app_services["task_repository"],
        confirmation_repository=app_services["confirmation_repository"],
        **kwargs,
    )


def _confirmation_service(app_services: dict[str, object]) -> ConfirmationService:
    repository = app_services["confirmation_repository"]
    assert isinstance(repository, ConfirmationRepository)
    return ConfirmationService(app_services["paths"], repository)


def _start_waiting_job(
    qtbot, app_services: dict[str, object], tmp_path: Path, *, name: str = "confirm.xlsx"
) -> tuple[TaskService, str]:
    source = tmp_path / name
    source.write_bytes(b"confirmation-source")
    service = _task_service(app_services)
    with qtbot.waitSignal(service.needs_confirmation, timeout=15_000):
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    return service, job_id


def _answer() -> ConfirmationAnswer:
    return ConfirmationAnswer(confirmation_id="mock-confirm-1", value="人工值")


def test_confirmation_resubmits_and_finishes_at_final_result_path(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])

    with qtbot.waitSignal(task_service.finished, timeout=15_000) as finished:
        task_service.finalize(job_id, bundle_path)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    task = task_repository.get(job_id)
    final_job = JobRequest.model_validate_json(
        (task_service.paths.tasks / job_id / "job-finalize.json").read_text(encoding="utf-8")
    )
    assert finished.args[0].status.value == "success"
    assert task["status"] == "success"
    assert Path(str(task["result_path"])) == Path(final_job.output_dir) / "result.json"
    assert Path(str(task["result_path"])).is_file()
    assert final_job.phase is JobPhase.FINALIZE
    assert final_job.parent_job_id == job_id
    assert Path(final_job.confirmation_file or "") == bundle_path.resolve()
    assert job_id not in task_service.runners
    with pytest.raises(InvalidTaskTransition):
        task_service.finalize(job_id, bundle_path)


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ([], "missing blocking confirmations"),
        ([_answer(), ConfirmationAnswer(confirmation_id="unknown", value="x")], "unknown"),
        ([_answer(), _answer()], "duplicate"),
    ],
)
def test_confirmation_submit_rejects_incomplete_or_untrusted_answer_ids(
    qtbot,
    app_services: dict[str, object],
    tmp_path: Path,
    answers: list[ConfirmationAnswer],
    message: str,
) -> None:
    _, job_id = _start_waiting_job(qtbot, app_services, tmp_path)

    with pytest.raises(ValueError, match=message):
        _confirmation_service(app_services).submit(job_id, answers)

    assert not (app_services["paths"].tasks / job_id / "confirmation.json").exists()
    repository = app_services["confirmation_repository"]
    assert isinstance(repository, ConfirmationRepository)
    assert all(record["answer"] is None for record in repository.list_for_job(job_id))


def test_confirmation_file_is_atomically_replaced_before_answers_are_saved(
    qtbot,
    app_services: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    repository = app_services["confirmation_repository"]
    assert isinstance(repository, ConfirmationRepository)
    target = app_services["paths"].tasks / job_id / "confirmation.json"
    observations: list[tuple[bool, list[Path]]] = []

    def fail_after_file_write(_job_id: str, _answers: list[ConfirmationAnswer]) -> None:
        temporary_files = list(target.parent.glob(".confirmation.json.*.tmp"))
        observations.append((target.is_file(), temporary_files))
        raise RuntimeError("simulated answer persistence failure")

    monkeypatch.setattr(repository, "save_answers", fail_after_file_write)

    with pytest.raises(RuntimeError, match="simulated answer persistence failure"):
        _confirmation_service(app_services).submit(job_id, [_answer()])

    assert observations == [(True, [])]
    stored_bundle = ConfirmationBundle.model_validate_json(
        target.read_text(encoding="utf-8")
    )
    assert stored_bundle.job_id == job_id


def test_finalize_rejects_bundle_for_a_different_job(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    first_service, first_job_id = _start_waiting_job(
        qtbot, app_services, tmp_path, name="confirm-first.xlsx"
    )
    _, second_job_id = _start_waiting_job(
        qtbot, app_services, tmp_path, name="confirm-second.xlsx"
    )
    confirmation_service = _confirmation_service(app_services)
    first_bundle = confirmation_service.submit(first_job_id, [_answer()])
    second_bundle = confirmation_service.submit(second_job_id, [_answer()])
    first_bundle.write_bytes(second_bundle.read_bytes())

    with pytest.raises(ValueError, match="bundle job_id"):
        first_service.finalize(first_job_id, first_bundle)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(first_job_id)["status"] == "waiting_confirmation"
    assert not (first_bundle.parent / "job-finalize.json").exists()


def test_finalize_rejects_file_answers_not_persisted_in_repository(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = task_service.paths.tasks / job_id / "confirmation.json"
    bundle_path.write_text(
        ConfirmationBundle(job_id=job_id, answers=[_answer()]).model_dump_json(indent=2),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stored answered state"):
        task_service.finalize(job_id, bundle_path)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(job_id)["status"] == "waiting_confirmation"
    assert not (bundle_path.parent / "job-finalize.json").exists()


class PassiveRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.started_paths: list[Path] = []

    def start(self, _module: object, job_path: Path) -> None:
        self.started_paths.append(job_path)


def test_finalize_prevents_overlapping_and_double_finalize(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    calls = 0
    created: list[PassiveRunner] = []

    def runner_factory() -> QObject:
        nonlocal calls
        calls += 1
        if calls == 1:
            from core.modules.process_runner import ModuleProcessRunner

            return ModuleProcessRunner()
        runner = PassiveRunner()
        created.append(runner)
        return runner

    source = tmp_path / "confirm-overlap.xlsx"
    source.write_bytes(b"confirmation-source")
    task_service = _task_service(app_services, runner_factory=runner_factory)
    with qtbot.waitSignal(task_service.needs_confirmation, timeout=15_000):
        job_id = task_service.create_and_start(ModuleId.MOISTURE, [source])
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])

    task_service.finalize(job_id, bundle_path)
    with pytest.raises(InvalidTaskTransition):
        task_service.finalize(job_id, bundle_path)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(job_id)["status"] == "running_finalize"
    assert len(created) == 1
    assert created[0].started_paths == [bundle_path.parent / "job-finalize.json"]


class FinalizeStartFailureRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def start(self, _module: object, _job_path: Path) -> None:
        raise RuntimeError("simulated finalize runner failure")


def test_finalize_runner_failure_is_terminal_once(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    calls = 0

    def runner_factory() -> QObject:
        nonlocal calls
        calls += 1
        if calls == 1:
            from core.modules.process_runner import ModuleProcessRunner

            return ModuleProcessRunner()
        return FinalizeStartFailureRunner()

    source = tmp_path / "confirm-failure.xlsx"
    source.write_bytes(b"confirmation-source")
    task_service = _task_service(app_services, runner_factory=runner_factory)
    with qtbot.waitSignal(task_service.needs_confirmation, timeout=15_000):
        job_id = task_service.create_and_start(ModuleId.MOISTURE, [source])
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    failures = QSignalSpy(task_service.failed)

    task_service.finalize(job_id, bundle_path)
    qtbot.wait(50)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert failures.count() == 1
    assert "simulated finalize runner failure" in failures.at(0)[1]
    assert task_repository.get(job_id)["status"] == "failed"
    assert job_id not in task_service.runners
    assert task_service._states == {}
    assert task_service._jobs == {}


def test_finalize_is_rejected_outside_waiting_confirmation(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source")
    task_service = _task_service(app_services)
    with qtbot.waitSignal(task_service.finished, timeout=15_000):
        job_id = task_service.create_and_start(ModuleId.MOISTURE, [source])
    bundle_path = task_service.paths.tasks / job_id / "confirmation.json"

    with pytest.raises(InvalidTaskTransition):
        task_service.finalize(job_id, bundle_path)


def test_finalize_job_file_is_atomic_and_valid_before_runner_start(
    qtbot,
    app_services: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replaced: list[Path] = []
    from core.tasks import service as task_service_module

    real_replace: Callable[[Path, Path], None] = task_service_module.os.replace

    def observed_replace(temporary: Path, target: Path) -> None:
        replaced.append(Path(target))
        real_replace(temporary, target)

    monkeypatch.setattr(task_service_module.os, "replace", observed_replace)
    calls = 0
    created: list[PassiveRunner] = []

    def runner_factory() -> QObject:
        nonlocal calls
        calls += 1
        if calls == 1:
            from core.modules.process_runner import ModuleProcessRunner

            return ModuleProcessRunner()
        runner = PassiveRunner()
        created.append(runner)
        return runner

    source = tmp_path / "confirm-atomic.xlsx"
    source.write_bytes(b"confirmation-source")
    task_service = _task_service(app_services, runner_factory=runner_factory)
    with qtbot.waitSignal(task_service.needs_confirmation, timeout=15_000):
        job_id = task_service.create_and_start(ModuleId.MOISTURE, [source])
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    final_path = bundle_path.parent / "job-finalize.json"

    task_service.finalize(job_id, bundle_path)

    assert final_path in replaced
    final_job = JobRequest.model_validate_json(final_path.read_text(encoding="utf-8"))
    assert final_job.phase is JobPhase.FINALIZE
    assert list(final_path.parent.glob(".job-finalize.json.*.tmp")) == []
