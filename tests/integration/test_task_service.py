from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.service import TaskService


def _service(app_services: dict[str, object], **kwargs: object) -> TaskService:
    return TaskService(
        paths=app_services["paths"],
        registry=app_services["registry"],
        task_repository=app_services["task_repository"],
        confirmation_repository=app_services["confirmation_repository"],
        **kwargs,
    )


def test_task_service_snapshots_input_persists_outputs_and_finishes(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source-bytes")
    service = _service(app_services)

    with qtbot.waitSignal(service.finished, timeout=15_000) as signal:
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    assert signal.args[0].status.value == "success"
    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    task = task_repository.get(job_id)
    files = task_repository.list_files(job_id)
    assert task["status"] == "success"
    assert Path(str(task["result_path"])).is_file()
    assert len(files) == 1
    assert Path(str(files[0]["snapshot_path"])).read_bytes() == b"source-bytes"
    assert files[0]["status"] == "snapshotted"
    assert len(task_repository.list_outputs(job_id)) == 3
    assert source.read_bytes() == b"source-bytes"
    assert job_id not in service.runners


def test_task_service_persists_confirmation_prompts_before_state_and_signal(
    qtbot, app_services: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"confirm-source")
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    statuses_seen_while_saving: list[str] = []
    original_save = confirmation_repository.save_prompts

    def save_prompts_in_order(job_id: str, prompts) -> None:
        statuses_seen_while_saving.append(str(task_repository.get(job_id)["status"]))
        original_save(job_id, prompts)

    monkeypatch.setattr(confirmation_repository, "save_prompts", save_prompts_in_order)
    service = _service(app_services)

    with qtbot.waitSignal(service.needs_confirmation, timeout=15_000) as signal:
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    assert signal.args[0] == job_id
    assert statuses_seen_while_saving == ["running_draft"]
    assert task_repository.get(job_id)["status"] == "waiting_confirmation"
    stored = confirmation_repository.list_for_job(job_id)
    assert [item["confirmation_id"] for item in stored] == ["mock-confirm-1"]
    assert job_id not in service.runners


def test_task_service_persists_partial_outputs(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "partial.xlsx"
    source.write_bytes(b"partial-source")
    service = _service(app_services)

    with qtbot.waitSignal(service.finished, timeout=15_000):
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(job_id)["status"] == "partial_success"
    assert len(task_repository.list_outputs(job_id)) == 3


@pytest.mark.parametrize("kind", ["none", "missing", "directory", "empty", "unsupported"])
def test_task_service_validation_failure_is_persisted_and_nonfatal(
    qtbot, app_services: dict[str, object], tmp_path: Path, kind: str
) -> None:
    source = tmp_path / "invalid.xlsx"
    if kind == "none":
        inputs: list[Path] = []
    elif kind == "missing":
        inputs = [source]
    elif kind == "directory":
        source.mkdir()
        inputs = [source]
    elif kind == "empty":
        source.touch()
        inputs = [source]
    else:
        source = tmp_path / "invalid.csv"
        source.write_bytes(b"csv")
        inputs = [source]
    service = _service(app_services)
    failures = QSignalSpy(service.failed)

    job_id = service.create_and_start(ModuleId.MOISTURE, inputs)
    qtbot.wait(50)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert failures.count() == 1
    assert failures.at(0)[0] == job_id
    assert task_repository.get(job_id)["status"] == "failed"
    assert task_repository.list_files(job_id) == []
    assert job_id not in service.runners


class StartFailureRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def start(self, _module: object, _job_path: Path) -> None:
        raise RuntimeError("simulated runner start failure")


def test_task_service_start_exception_is_persisted_and_emitted_once(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source")
    factory: Callable[[], StartFailureRunner] = StartFailureRunner
    service = _service(app_services, runner_factory=factory)
    failures = QSignalSpy(service.failed)

    job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    qtbot.wait(50)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert failures.count() == 1
    assert "simulated runner start failure" in failures.at(0)[1]
    assert task_repository.get(job_id)["status"] == "failed"
    assert len(task_repository.list_files(job_id)) == 1
    assert job_id not in service.runners


def test_task_service_runs_two_concurrent_jobs_with_distinct_runners(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    first = tmp_path / "normal-first.xlsx"
    second = tmp_path / "normal-second.xlsx"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    created_runners: list[object] = []

    from core.modules.process_runner import ModuleProcessRunner

    def runner_factory() -> ModuleProcessRunner:
        runner = ModuleProcessRunner()
        created_runners.append(runner)
        return runner

    service = _service(app_services, runner_factory=runner_factory)
    finished = QSignalSpy(service.finished)

    first_job = service.create_and_start(ModuleId.MOISTURE, [first])
    second_job = service.create_and_start(ModuleId.MOISTURE, [second])
    assert first_job != second_job
    assert set(service.runners) == {first_job, second_job}
    qtbot.waitUntil(lambda: finished.count() == 2, timeout=15_000)
    qtbot.wait(50)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert len(created_runners) == 2
    assert created_runners[0] is not created_runners[1]
    assert task_repository.get(first_job)["status"] == "success"
    assert task_repository.get(second_job)["status"] == "success"
    assert service.runners == {}
