import json
from dataclasses import replace
from pathlib import Path

import pytest
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


def test_waiting_confirmation_preserves_module_config_across_restart(
    qtbot, tmp_path: Path
) -> None:
    root = tmp_path / "restart-config-data"
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"mock")
    first = build_context(root, use_mocks=True)
    try:
        waiting = QSignalSpy(first.task_service.needs_confirmation)
        job_id = first.task_service.create_and_start(
            ModuleId.MOISTURE,
            [source],
            {"default_year": 2026},
        )
        assert waiting.wait(15_000)
    finally:
        first.close()

    second = build_context(root, use_mocks=True)
    try:
        pending = second.task_service.pending_confirmations()
        assert [item[0] for item in pending] == [job_id]
        recovered = second.task_service._jobs[job_id]
        assert recovered.module_config_file == str(
            (second.paths.tasks / job_id / "module-config.json").resolve()
        )
    finally:
        second.close()


def test_waiting_recovery_rejects_modified_module_config(qtbot, tmp_path: Path) -> None:
    root = tmp_path / "tampered-module-config"
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"mock")
    first = build_context(root, use_mocks=True)
    waiting = QSignalSpy(first.task_service.needs_confirmation)
    job_id = first.task_service.create_and_start(
        ModuleId.MOISTURE,
        [source],
        {"default_year": 2026},
    )
    assert waiting.wait(15_000)
    (first.paths.tasks / job_id / "module-config.json").write_text(
        '{"default_year":2025}',
        encoding="utf-8",
    )
    first.close()

    second = build_context(root, use_mocks=True)
    try:
        assert second.task_repository.get(job_id)["status"] == "failed"
        assert second.task_service.pending_confirmations() == []
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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_mode", "batch"),
        ("ai_enabled", True),
        ("allowed_knowledge_scopes", ["moisture", "shared"]),
        ("module_config_file", "task-file"),
        ("service_response_file", "task-file"),
        ("parent_job_id", "unexpected-parent"),
        ("confirmation_file", "task-file"),
    ],
)
def test_waiting_recovery_rejects_noncanonical_draft_fields(
    qtbot, tmp_path: Path, field: str, value: object
) -> None:
    root = tmp_path / f"tampered-{field}"
    source = tmp_path / f"{field}-confirm.xlsx"
    source.write_bytes(b"mock")
    first = build_context(root, use_mocks=True)
    waiting = QSignalSpy(first.task_service.needs_confirmation)
    job_id = first.task_service.create_and_start(ModuleId.MOISTURE, [source])
    assert waiting.wait(15_000)
    draft_path = first.paths.tasks / job_id / "job-draft.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if value == "task-file":
        value = str((draft_path.parent / "unexpected.json").resolve())
    draft[field] = value
    draft_path.write_text(json.dumps(draft), encoding="utf-8")
    first.close()

    second = build_context(root, use_mocks=True)
    try:
        record = second.task_repository.get(job_id)
        assert record["status"] == "failed"
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


@pytest.mark.parametrize(
    "status",
    ["waiting_confirmation", "success", "partial_success", "failed", "cancelled"],
)
def test_terminal_marker_never_overwrites_waiting_or_terminal_task(
    app_services: dict[str, object], status: str
) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    job_id = f"marker-{status.replace('_', '-')}"
    task_dir = app_services["paths"].tasks / job_id
    task_dir.mkdir()
    task_repository.create(job_id, ModuleId.MOISTURE.value, status, "2026-07-13T10:00:00+08:00")
    marker = task_dir / ".terminal-pending.json"
    marker.write_text(
        json.dumps({"job_id": job_id, "status": "failed", "error": "attacker"}),
        encoding="utf-8",
    )

    service._apply_terminal_markers()

    assert task_repository.get(job_id)["status"] == status
    assert marker.is_file()


@pytest.mark.parametrize("payload_kind", ["extra", "missing"])
def test_terminal_marker_requires_exact_payload_keys(
    app_services: dict[str, object], payload_kind: str
) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    job_id = f"payload-{payload_kind}-001"
    task_dir = app_services["paths"].tasks / job_id
    task_dir.mkdir()
    task_repository.create(
        job_id, ModuleId.MOISTURE.value, "running_draft", "2026-07-13T10:00:00+08:00"
    )
    payload = {"job_id": job_id, "status": "failed", "error": "fault"}
    if payload_kind == "extra":
        payload["unexpected"] = "untrusted"
    else:
        payload.pop("error")
    marker = task_dir / ".terminal-pending.json"
    marker.write_text(json.dumps(payload), encoding="utf-8")

    service._apply_terminal_markers()

    assert task_repository.get(job_id)["status"] == "running_draft"
    assert marker.is_file()


def test_terminal_marker_rejects_simulated_linked_parent_for_read_and_write(
    app_services: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    job_id = "linked-parent-001"
    task_dir = app_services["paths"].tasks / job_id
    task_dir.mkdir()
    task_repository.create(
        job_id, ModuleId.MOISTURE.value, "running_draft", "2026-07-13T10:00:00+08:00"
    )
    marker = task_dir / ".terminal-pending.json"
    marker.write_text(
        json.dumps({"job_id": job_id, "status": "failed", "error": "external"}),
        encoding="utf-8",
    )
    original_is_symlink = Path.is_symlink

    def simulated_parent_link(path: Path) -> bool:
        if path == task_dir:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", simulated_parent_link)

    service._apply_terminal_markers()
    with pytest.raises(ValueError, match="link"):
        service._write_terminal_marker(job_id, TaskLifecycleState.FAILED, "write")

    assert task_repository.get(job_id)["status"] == "running_draft"
    assert json.loads(marker.read_text(encoding="utf-8"))["error"] == "external"


def test_terminal_marker_write_rejects_invalid_job_escape(app_services: dict[str, object]) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    outside = app_services["paths"].tasks.parent / "escape"
    outside.mkdir()

    with pytest.raises(ValueError, match="job ID"):
        service._write_terminal_marker("../escape", TaskLifecycleState.FAILED, "escape")

    assert not (outside / ".terminal-pending.json").exists()


def test_terminal_marker_never_reads_or_deletes_through_real_task_link(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    job_id = "real-linked-task-001"
    external_dir = tmp_path / "external" / job_id
    external_dir.mkdir(parents=True)
    external_marker = external_dir / ".terminal-pending.json"
    external_marker.write_text(
        json.dumps({"job_id": job_id, "status": "failed", "error": "outside"}),
        encoding="utf-8",
    )
    task_link = app_services["paths"].tasks / job_id
    try:
        task_link.symlink_to(external_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")
    task_repository.create(
        job_id, ModuleId.MOISTURE.value, "running_draft", "2026-07-13T10:00:00+08:00"
    )

    service._apply_terminal_markers()

    assert task_repository.get(job_id)["status"] == "running_draft"
    assert external_marker.is_file()


def test_terminal_marker_rejects_simulated_linked_tasks_root_for_read_and_write(
    app_services: dict[str, object], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    job_id = "linked-tasks-root-001"
    external_tasks = tmp_path / "external-tasks"
    task_dir = external_tasks / job_id
    task_dir.mkdir(parents=True)
    marker = task_dir / ".terminal-pending.json"
    marker.write_text(
        json.dumps({"job_id": job_id, "status": "failed", "error": "outside"}),
        encoding="utf-8",
    )
    task_repository.create(
        job_id, ModuleId.MOISTURE.value, "running_draft", "2026-07-13T10:00:00+08:00"
    )
    service.paths = replace(app_services["paths"], tasks=external_tasks)
    original_is_symlink = Path.is_symlink

    def simulated_tasks_root_link(path: Path) -> bool:
        if path == external_tasks:
            return True
        return original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", simulated_tasks_root_link)

    service._apply_terminal_markers()
    with pytest.raises(ValueError, match="tasks root.*link"):
        service._write_terminal_marker(job_id, TaskLifecycleState.FAILED, "write")

    assert task_repository.get(job_id)["status"] == "running_draft"
    assert json.loads(marker.read_text(encoding="utf-8"))["error"] == "outside"


def test_terminal_marker_never_reads_or_deletes_through_real_tasks_root_link(
    app_services: dict[str, object], tmp_path: Path
) -> None:
    task_repository = app_services["task_repository"]
    confirmation_repository = app_services["confirmation_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert isinstance(confirmation_repository, ConfirmationRepository)
    service = TaskService(
        app_services["paths"],
        app_services["registry"],
        task_repository,
        confirmation_repository,
    )
    job_id = "real-linked-tasks-root-001"
    external_tasks = tmp_path / "external-tasks-root"
    task_dir = external_tasks / job_id
    task_dir.mkdir(parents=True)
    marker = task_dir / ".terminal-pending.json"
    marker.write_text(
        json.dumps({"job_id": job_id, "status": "failed", "error": "outside"}),
        encoding="utf-8",
    )
    task_repository.create(
        job_id, ModuleId.MOISTURE.value, "running_draft", "2026-07-13T10:00:00+08:00"
    )
    tasks_link = app_services["paths"].root / "tasks-root-link"
    try:
        tasks_link.symlink_to(external_tasks, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")
    service.paths = replace(app_services["paths"], tasks=tasks_link)

    service._apply_terminal_markers()

    assert task_repository.get(job_id)["status"] == "running_draft"
    assert marker.is_file()
