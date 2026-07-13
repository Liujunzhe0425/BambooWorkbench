from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from app.bootstrap import build_context
from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.enums import ModuleId
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.models import TaskLifecycleState
from core.tasks.service import TaskService


class CrashingStartRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def start(self, _module: object, _job_path: Path) -> None:
        raise RuntimeError("simulated start crash")


def test_waiting_confirmation_survives_real_context_restart(qtbot, tmp_path: Path) -> None:
    root = tmp_path / "restart-data"
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"mock")
    first = build_context(root, use_mocks=True)
    try:
        waiting = QSignalSpy(first.task_service.needs_confirmation)
        job_id = first.task_service.create_and_start(ModuleId.MOISTURE, [source])
        assert waiting.wait(15_000)
    finally:
        first.close()

    second = build_context(root, use_mocks=True)
    try:
        pending = second.task_service.pending_confirmations()
        assert [item[0] for item in pending] == [job_id]
        bundle = second.confirmation_service.submit(
            job_id,
            [ConfirmationAnswer(confirmation_id="mock-confirm-1", value="人工值")],
        )
        finished = QSignalSpy(second.task_service.finished)
        second.task_service.finalize(job_id, bundle)
        assert finished.wait(15_000)
        assert second.task_repository.get(job_id)["status"] == "success"
    finally:
        second.close()


def test_context_shutdown_cancels_real_active_job_before_database_close(
    qtbot, tmp_path: Path
) -> None:
    root = tmp_path / "shutdown-data"
    source = tmp_path / "timeout.xlsx"
    source.write_bytes(b"mock")
    context = build_context(root, use_mocks=True)
    job_id = context.task_service.create_and_start(ModuleId.MOISTURE, [source])
    qtbot.waitUntil(lambda: job_id in context.task_service.runners, timeout=2_000)

    context.close()

    database = Database.open(context.paths)
    try:
        repository = TaskRepository(database)
        assert repository.get(job_id)["status"] == "cancelled"
    finally:
        database.close()


def test_invalid_waiting_confirmation_recovery_becomes_failed(qtbot, tmp_path: Path) -> None:
    root = tmp_path / "invalid-recovery-data"
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"mock")
    first = build_context(root, use_mocks=True)
    waiting = QSignalSpy(first.task_service.needs_confirmation)
    job_id = first.task_service.create_and_start(ModuleId.MOISTURE, [source])
    assert waiting.wait(15_000)
    draft_path = first.paths.tasks / job_id / "job-draft.json"
    draft_path.write_text("{}", encoding="utf-8")
    first.close()

    second = build_context(root, use_mocks=True)
    try:
        record = second.task_repository.get(job_id)
        assert record["status"] == "failed"
        assert "recovery failed" in str(record["error"])
        assert second.task_service.pending_confirmations() == []
    finally:
        second.close()


def test_bootstrap_reconciles_interrupted_jobs_and_terminal_marker(tmp_path: Path) -> None:
    root = tmp_path / "restart-data"
    first = build_context(root, use_mocks=False)
    repository = first.task_repository
    now = "2026-07-13T10:00:00+08:00"
    for status in ("created", "running_draft", "running_finalize"):
        job_id = f"interrupted-{status}"
        (first.paths.tasks / job_id).mkdir()
        repository.create(job_id, ModuleId.MOISTURE.value, status, now)
    marker_job = "marker-job-001"
    marker_dir = first.paths.tasks / marker_job
    marker_dir.mkdir()
    repository.create(marker_job, ModuleId.MOISTURE.value, "running_draft", now)
    (marker_dir / ".terminal-pending.json").write_text(
        '{"job_id":"marker-job-001","status":"failed","error":"durable failure"}',
        encoding="utf-8",
    )
    first.close()

    second = build_context(root, use_mocks=False)
    try:
        for status in ("created", "running_draft", "running_finalize"):
            record = second.task_repository.get(f"interrupted-{status}")
            assert record["status"] == "failed"
            assert "interrupted" in str(record["error"])
        assert second.task_repository.get(marker_job)["status"] == "failed"
        assert second.task_repository.get(marker_job)["error"] == "durable failure"
        assert not (marker_dir / ".terminal-pending.json").exists()
    finally:
        second.close()


def test_terminal_marker_repairs_database_in_new_service_context(
    app_services: dict[str, object], tmp_path: Path, monkeypatch
) -> None:
    paths = app_services["paths"]
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        paths,
        app_services["registry"],
        task_repository,
        confirmation_repository,
        runner_factory=CrashingStartRunner,
    )
    original = task_repository.update_status

    def fail_terminal(job_id: str, status: str, **kwargs: object) -> None:
        if status == TaskLifecycleState.FAILED.value:
            raise OSError("database unavailable")
        original(job_id, status, **kwargs)

    monkeypatch.setattr(task_repository, "update_status", fail_terminal)
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    monkeypatch.setattr(task_repository, "update_status", original)

    repaired = TaskService(
        paths,
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )

    assert task_repository.get(job_id)["status"] == "failed"
    assert job_id not in repaired._states
    assert job_id not in repaired._jobs
    assert not (paths.tasks / job_id / ".terminal-pending.json").exists()
