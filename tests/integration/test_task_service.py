import json
import sqlite3
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.tasks import TaskRepository
from core.storage.settings import SettingsStore
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


def test_module_config_requires_declared_ai_report_capability(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "summary.xlsx"
    source.write_bytes(b"source")
    service = _service(app_services)

    with pytest.raises(ValueError, match="不支持独立 AI"):
        service.create_and_start(
            ModuleId.MOISTURE,
            [source],
            module_config={"schema_version": "1.0", "operation": "ai_report"},
        )


def test_supported_ai_report_config_is_task_local_and_contains_no_secret(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    registry = app_services["registry"]
    module = registry.get(ModuleId.MOISTURE)
    registry._modules[ModuleId.MOISTURE] = replace(
        module,
        manifest=module.manifest.model_copy(update={"capabilities": ["ai_report"]}),
    )
    source = tmp_path / "summary.xlsx"
    source.write_bytes(b"source")
    service = _service(app_services)
    config = {
        "schema_version": "1.0",
        "operation": "ai_report",
        "question": "请给出复核提示",
    }

    with qtbot.waitSignal(service.finished, timeout=15_000):
        job_id = service.create_and_start(
            ModuleId.MOISTURE,
            [source],
            module_config=config,
        )

    config_path = app_services["paths"].tasks / job_id / "module-config.json"
    assert json.loads(config_path.read_text(encoding="utf-8")) == config
    assert "api_key" not in config_path.read_text(encoding="utf-8").casefold()


def test_incremental_config_requires_manifest_declaration_and_exact_roles(
    app_services: dict[str, object],
) -> None:
    registry = app_services["registry"]
    module = registry.get(ModuleId.MOISTURE)
    config = {
        "schema_version": "1.0",
        "operation": "append_summary",
        "inputs": [
            {"role": "base_summary", "input_index": 0},
            {"role": "new_raw", "input_index": 1},
        ],
    }
    undeclared = replace(
        module,
        manifest=module.manifest.model_copy(update={"supports_incremental": False}),
    )
    with pytest.raises(ValueError, match="尚未声明"):
        TaskService._validate_module_config_support(
            ModuleId.MOISTURE,
            undeclared,
            config,
            input_count=2,
        )

    incremental = replace(
        module,
        manifest=module.manifest.model_copy(update={"supports_incremental": True}),
    )
    TaskService._validate_module_config_support(
        ModuleId.MOISTURE,
        incremental,
        config,
        input_count=2,
    )
    with pytest.raises(ValueError, match="完整且不重复"):
        TaskService._validate_module_config_support(
            ModuleId.MOISTURE,
            incremental,
            {
                **config,
                "inputs": [
                    {"role": "base_summary", "input_index": 0},
                    {"role": "new_raw", "input_index": 0},
                ],
            },
            input_count=2,
        )


def test_task_service_publishes_outputs_after_module_finishes(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source-bytes")
    output_root = tmp_path / "published"
    settings = SettingsStore(app_services["database"])
    settings.set("output_dir", str(output_root))
    service = _service(app_services, settings=settings)

    with qtbot.waitSignal(service.finished, timeout=15_000) as signal:
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    folders = [path for path in output_root.iterdir() if path.is_dir()]
    assert len(folders) == 1
    assert not folders[0].name.startswith("000001-")
    assert not (folders[0] / "result.json").exists()
    assert all(Path(output.path).is_relative_to(folders[0]) for output in signal.args[0].outputs)
    stored = app_services["task_repository"].list_outputs(job_id)
    assert all(Path(str(output["path"])).is_relative_to(folders[0]) for output in stored)


def test_publication_failure_keeps_internal_outputs_and_warns(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source-bytes")
    invalid_root = tmp_path / "not-a-directory"
    invalid_root.write_text("occupied", encoding="utf-8")
    settings = SettingsStore(app_services["database"])
    settings.set("output_dir", str(invalid_root))
    service = _service(app_services, settings=settings)

    with (
        qtbot.waitSignal(service.publication_warning, timeout=15_000) as warning,
        qtbot.waitSignal(service.finished, timeout=15_000) as finished,
    ):
        service.create_and_start(ModuleId.MOISTURE, [source])

    assert "已保留" in warning.args[1]
    assert finished.args[0].status.value == "success"
    assert all(Path(output.path).is_file() for output in finished.args[0].outputs)


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
    assert job_id in service._states
    assert job_id in service._jobs


def test_task_service_persists_partial_outputs(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "partial.xlsx"
    source.write_bytes(b"partial-source")
    successful_source = tmp_path / "normal.xlsx"
    successful_source.write_bytes(b"normal-source")
    service = _service(app_services)

    with qtbot.waitSignal(service.finished, timeout=15_000):
        job_id = service.create_and_start(
            ModuleId.MOISTURE,
            [source, successful_source],
        )

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(job_id)["status"] == "partial_success"
    assert len(task_repository.list_outputs(job_id)) == 3


def test_task_service_removes_batch_snapshots_when_file_index_insert_fails(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "duplicate.xlsx"
    source.write_bytes(b"duplicate-source")
    service = _service(app_services)
    failures = QSignalSpy(service.failed)

    job_id = service.create_and_start(ModuleId.MOISTURE, [source, source])

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert failures.count() == 1
    assert task_repository.get(job_id)["status"] == "failed"
    assert task_repository.list_files(job_id) == []
    assert not (service.paths.tasks / job_id / "inputs").exists()


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
    assert service._states == {}
    assert service._jobs == {}
    assert service._failed_signals == set()


class StartFailureRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def start(self, _module: object, _job_path: Path) -> None:
        raise RuntimeError("simulated runner start failure")


class _PassiveSignal:
    def connect(self, _callback: object) -> None:
        pass


class _RejectingSignal:
    def __init__(self, runner: "ConnectionFailureRunner") -> None:
        self.runner = runner

    def connect(self, _callback: object) -> None:
        self.runner.was_registered_at_connect = any(
            active is self.runner for active in self.runner.service.runners.values()
        )
        raise RuntimeError("simulated signal connection failure")


class ConnectionFailureRunner:
    def __init__(self, service: TaskService) -> None:
        self.service = service
        self.progress = _RejectingSignal(self)
        self.completed = _PassiveSignal()
        self.failed = _PassiveSignal()
        self.cancelled = _PassiveSignal()
        self.was_registered_at_connect = False
        self.delete_requested = False

    def start(self, _module: object, _job_path: Path) -> None:
        raise AssertionError("start must not run after a connection failure")

    def deleteLater(self) -> None:
        self.delete_requested = True


def test_task_service_registers_runner_before_connection_failure_cleanup(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source")
    created: list[ConnectionFailureRunner] = []
    service: TaskService

    def runner_factory() -> ConnectionFailureRunner:
        runner = ConnectionFailureRunner(service)
        created.append(runner)
        return runner

    service = _service(app_services, runner_factory=runner_factory)
    failures = QSignalSpy(service.failed)

    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert failures.count() == 1
    assert "simulated signal connection failure" in failures.at(0)[1]
    assert task_repository.get(job_id)["status"] == "failed"
    assert created[0].was_registered_at_connect
    assert created[0].delete_requested
    assert service.runners == {}
    assert service._states == {}
    assert service._jobs == {}
    assert service._failed_signals == set()


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
    assert UUID(first_job).version == 4
    assert UUID(second_job).version == 4
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


def test_task_service_restart_collision_cleans_owned_directory_and_raises(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    collision_id = "collision-job-0001"
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source")
    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    task_repository.create(
        collision_id,
        ModuleId.MOISTURE.value,
        "created",
        "2026-07-13T12:00:00+08:00",
    )
    service = _service(app_services, job_id_factory=lambda: collision_id)
    failures = QSignalSpy(service.failed)

    with pytest.raises(sqlite3.IntegrityError):
        service.create_and_start(ModuleId.MOISTURE, [source])

    assert not (service.paths.tasks / collision_id).exists()
    assert task_repository.get(collision_id)["created_at"] == "2026-07-13T12:00:00+08:00"
    assert failures.count() == 0


def test_task_service_terminal_metadata_stays_bounded_after_many_jobs(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    service = _service(app_services)
    finished = QSignalSpy(service.finished)
    job_ids: list[str] = []
    for index in range(6):
        source = tmp_path / f"normal-{index}.xlsx"
        source.write_bytes(f"source-{index}".encode())
        job_ids.append(service.create_and_start(ModuleId.MOISTURE, [source]))

    qtbot.waitUntil(lambda: finished.count() == len(job_ids), timeout=20_000)

    assert service.runners == {}
    assert service._states == {}
    assert service._jobs == {}
    assert service._failed_signals == set()
