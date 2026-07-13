import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Qt, Signal

from core.contracts.enums import ModuleId
from core.storage.repositories.tasks import TaskRepository
from core.tasks.models import InvalidTaskTransition, TaskLifecycleState
from core.tasks.service import TaskService
from ui.main_window import MainWindow


class ControlledRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls = 0

    def start(self, _module: object, _job_path: Path) -> None:
        pass

    def cancel(self) -> bool:
        self.cancel_calls += 1
        return True

    def confirm_cancelled(self) -> None:
        self.cancelled.emit()


class CrashingStartRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def start(self, _module: object, _job_path: Path) -> None:
        raise RuntimeError("simulated start crash")


class RejectingCancelRunner(ControlledRunner):
    def cancel(self) -> bool:
        self.cancel_calls += 1
        return False


class SynchronousCancelRunner(ControlledRunner):
    def cancel(self) -> bool:
        self.cancel_calls += 1
        self.cancelled.emit()
        return True


class FailedShutdownRunner(ControlledRunner):
    def __init__(self) -> None:
        super().__init__()
        self.shutdown_calls = 0

    def shutdown(self) -> bool:
        self.shutdown_calls += 1
        return False


def _service(app_services: dict[str, object], **kwargs: object) -> TaskService:
    return TaskService(
        paths=app_services["paths"],
        registry=app_services["registry"],
        task_repository=app_services["task_repository"],
        confirmation_repository=app_services["confirmation_repository"],
        **kwargs,
    )


def test_cancel_requests_active_runner_and_persists_only_after_confirmation(
    app_services: dict[str, object],
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    runners: list[ControlledRunner] = []

    def runner_factory() -> ControlledRunner:
        runner = ControlledRunner()
        runners.append(runner)
        return runner

    service = _service(app_services, runner_factory=runner_factory)
    repository = app_services["task_repository"]
    assert isinstance(repository, TaskRepository)
    observed_statuses: list[str] = []
    persisted_during_signal: list[str] = []
    service.status_changed.connect(
        lambda job_id, status: (
            observed_statuses.append(status),
            persisted_during_signal.append(str(repository.get(job_id)["status"])),
        )
    )
    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    service.cancel(job_id)

    assert runners[0].cancel_calls == 1
    assert repository.get(job_id)["status"] == TaskLifecycleState.RUNNING_DRAFT.value
    assert job_id in service.runners
    with pytest.raises(InvalidTaskTransition, match="pending"):
        service.cancel(job_id)
    assert runners[0].cancel_calls == 1
    assert repository.get(job_id)["status"] == TaskLifecycleState.RUNNING_DRAFT.value

    runners[0].confirm_cancelled()

    assert repository.get(job_id)["status"] == TaskLifecycleState.CANCELLED.value
    assert observed_statuses[-1] == TaskLifecycleState.CANCELLED.value
    assert persisted_during_signal[-1] == TaskLifecycleState.CANCELLED.value
    assert job_id not in service.runners


def test_inactive_cancel_is_safe_and_does_not_rewrite_terminal_task(
    app_services: dict[str, object],
) -> None:
    repository = app_services["task_repository"]
    assert isinstance(repository, TaskRepository)
    repository.create(
        "terminal-job-001",
        ModuleId.MOISTURE.value,
        TaskLifecycleState.SUCCESS.value,
        "2026-07-13T10:00:00+08:00",
    )
    service = _service(app_services)

    with pytest.raises(InvalidTaskTransition, match="active"):
        service.cancel("terminal-job-001")

    assert repository.get("terminal-job-001")["status"] == TaskLifecycleState.SUCCESS.value


def test_rejected_cancel_does_not_leave_service_pending(
    app_services: dict[str, object],
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    service = _service(app_services, runner_factory=RejectingCancelRunner)
    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    with pytest.raises(InvalidTaskTransition, match="not accepted"):
        service.cancel(job_id)

    assert job_id not in service._cancellation_pending
    assert job_id in service.runners


def test_synchronous_cancel_confirmation_clears_pending_and_runner(
    app_services: dict[str, object],
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    service = _service(app_services, runner_factory=SynchronousCancelRunner)
    repository = app_services["task_repository"]
    assert isinstance(repository, TaskRepository)
    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    service.cancel(job_id)

    assert repository.get(job_id)["status"] == TaskLifecycleState.CANCELLED.value
    assert job_id not in service._cancellation_pending
    assert job_id not in service.runners


def test_rejected_cancel_restores_ui_button_and_shows_nonmodal_error(
    qtbot,
    app_context,
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    app_context.task_service.runner_factory = RejectingCancelRunner
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    job_id = app_context.task_service.create_and_start(ModuleId.MOISTURE, [source])
    window.task_progress_page.bind(job_id)
    window.stack.setCurrentWidget(window.task_progress_page)

    qtbot.mouseClick(window.task_progress_page.cancel_button, Qt.MouseButton.LeftButton)

    assert window.task_progress_page.cancel_button.isEnabled()
    assert job_id not in app_context.task_service._cancellation_pending
    assert window.failure_messages
    assert not window.failure_messages[-1].isModal()


def test_failure_persistence_and_status_notification_precede_failed_signal(
    app_services: dict[str, object],
    tmp_path: Path,
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    service = _service(app_services, runner_factory=CrashingStartRunner)
    repository = app_services["task_repository"]
    assert isinstance(repository, TaskRepository)
    events: list[tuple[str, str]] = []
    service.status_changed.connect(
        lambda job_id, status: events.append(
            (f"status:{status}", str(repository.get(job_id)["status"]))
        )
    )
    service.failed.connect(
        lambda job_id, _message: events.append(("failed", str(repository.get(job_id)["status"])))
    )

    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    assert repository.get(job_id)["status"] == TaskLifecycleState.FAILED.value
    assert events[-2:] == [
        ("status:failed", TaskLifecycleState.FAILED.value),
        ("failed", TaskLifecycleState.FAILED.value),
    ]


def test_failed_status_persistence_error_uses_non_lifecycle_signal_and_keeps_context(
    app_services: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    service = _service(app_services, runner_factory=CrashingStartRunner)
    repository = app_services["task_repository"]
    assert isinstance(repository, TaskRepository)
    update_status = repository.update_status

    def fail_failed_transition(job_id: str, status: str, **kwargs: object) -> None:
        if status == TaskLifecycleState.FAILED.value:
            raise OSError("database unavailable")
        update_status(job_id, status, **kwargs)

    monkeypatch.setattr(repository, "update_status", fail_failed_transition)
    statuses: list[str] = []
    failures: list[tuple[str, str]] = []
    orchestration_errors: list[tuple[str, str]] = []
    service.status_changed.connect(lambda _job_id, status: statuses.append(status))
    service.failed.connect(lambda job_id, message: failures.append((job_id, message)))
    service.orchestration_error.connect(
        lambda job_id, message: orchestration_errors.append((job_id, message))
    )

    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    assert repository.get(job_id)["status"] == TaskLifecycleState.RUNNING_DRAFT.value
    assert statuses == [TaskLifecycleState.RUNNING_DRAFT.value]
    assert failures == []
    assert orchestration_errors and orchestration_errors[0][0] == job_id
    assert "database unavailable" in orchestration_errors[0][1]
    assert job_id not in service.runners
    assert job_id not in service._states
    assert job_id not in service._jobs
    marker = service.paths.tasks / job_id / ".terminal-pending.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "job_id": job_id,
        "status": "failed",
        "error": "task orchestration failed: RuntimeError: simulated start crash",
    }


def test_status_changed_payload_is_lifecycle_value_string(
    app_services: dict[str, object],
    tmp_path: Path,
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    service = _service(app_services, runner_factory=ControlledRunner)
    payloads: list[tuple[str, str]] = []
    service.status_changed.connect(lambda job_id, status: payloads.append((job_id, status)))

    job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    assert service.metaObject().indexOfSignal("status_changed(QString,QString)") >= 0
    assert payloads == [(job_id, TaskLifecycleState.RUNNING_DRAFT.value)]
    assert type(payloads[0][1]) is str


def test_shutdown_cleanup_failure_persists_failed_retains_runner_and_blocks_callbacks(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    service = _service(app_services, runner_factory=FailedShutdownRunner)
    repository = app_services["task_repository"]
    assert isinstance(repository, TaskRepository)
    job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    runner = service.runners[job_id]
    assert isinstance(runner, FailedShutdownRunner)

    assert service.shutdown() is False
    runner.completed.emit(object())

    record = repository.get(job_id)
    assert record["status"] == "failed"
    assert "cleanup" in str(record["error"])
    assert service.runners[job_id] is runner
    assert runner.shutdown_calls == 1


def test_failed_status_persistence_error_restores_ui_with_nonmodal_error(
    qtbot,
    app_context,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    app_context.task_service.runner_factory = CrashingStartRunner
    update_status = app_context.task_repository.update_status

    def fail_failed_transition(job_id: str, status: str, **kwargs: object) -> None:
        if status == TaskLifecycleState.FAILED.value:
            raise OSError("database unavailable")
        update_status(job_id, status, **kwargs)

    monkeypatch.setattr(
        app_context.task_repository,
        "update_status",
        fail_failed_transition,
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.workbench_page.module_selected.emit(ModuleId.MOISTURE)
    window.module_task_page.add_files([source])

    qtbot.mouseClick(window.module_task_page.run_button, Qt.MouseButton.LeftButton)

    job_id = app_context.task_repository.list_recent(1)[0]["job_id"]
    assert app_context.task_repository.get(job_id)["status"] == "running_draft"
    assert window.stack.currentWidget() is window.module_task_page
    assert window.task_progress_page.current_job_id == ""
    assert window.failure_messages
    assert not window.failure_messages[-1].isModal()
    assert "任务协调错误" in window.failure_messages[-1].windowTitle()
    assert window.isEnabled()


def test_main_window_disables_repeated_cancellation_until_terminal(
    qtbot,
    app_context,
    tmp_path: Path,
) -> None:
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    runners: list[ControlledRunner] = []

    def runner_factory() -> ControlledRunner:
        runner = ControlledRunner()
        runners.append(runner)
        return runner

    app_context.task_service.runner_factory = runner_factory
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    job_id = app_context.task_service.create_and_start(ModuleId.MOISTURE, [source])
    window.task_progress_page.bind(job_id)
    window.stack.setCurrentWidget(window.task_progress_page)

    qtbot.mouseClick(
        window.task_progress_page.cancel_button,
        Qt.MouseButton.LeftButton,
    )
    qtbot.mouseClick(
        window.task_progress_page.cancel_button,
        Qt.MouseButton.LeftButton,
    )

    assert runners[0].cancel_calls == 1
    assert not window.task_progress_page.cancel_button.isEnabled()
    runners[0].confirm_cancelled()
    assert window.task_progress_page.current_job_id == ""
    assert "取消" in window.task_progress_page.message_label.text()
    assert window.isEnabled()


def test_inactive_cancellation_is_a_nonmodal_ui_error(
    qtbot,
    app_context,
) -> None:
    app_context.task_repository.create(
        "terminal-job-002",
        ModuleId.MOISTURE.value,
        TaskLifecycleState.SUCCESS.value,
        "2026-07-13T10:00:00+08:00",
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.task_progress_page.bind("terminal-job-002")
    window.stack.setCurrentWidget(window.task_progress_page)

    qtbot.mouseClick(
        window.task_progress_page.cancel_button,
        Qt.MouseButton.LeftButton,
    )

    assert app_context.task_repository.get("terminal-job-002")["status"] == "success"
    assert window.failure_messages
    assert not window.failure_messages[-1].isModal()
    assert window.isEnabled()


def test_crashed_module_does_not_close_application(
    qtbot,
    app_context,
    tmp_path: Path,
) -> None:
    source = tmp_path / "crash.xlsx"
    source.write_bytes(b"mock")

    with qtbot.waitSignal(app_context.task_service.failed, timeout=15_000):
        app_context.task_service.create_and_start(ModuleId.MOISTURE, [source])

    assert app_context.task_repository.list_recent(1)[0]["status"] == "failed"
