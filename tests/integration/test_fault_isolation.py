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

    def cancel(self) -> None:
        self.cancel_calls += 1

    def confirm_cancelled(self) -> None:
        self.cancelled.emit()


class CrashingStartRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def start(self, _module: object, _job_path: Path) -> None:
        raise RuntimeError("simulated start crash")


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
    observed_statuses: list[TaskLifecycleState] = []
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
    assert observed_statuses[-1] is TaskLifecycleState.CANCELLED
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
            (f"status:{status.value}", str(repository.get(job_id)["status"]))
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
