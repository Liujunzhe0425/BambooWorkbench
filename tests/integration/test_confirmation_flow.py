import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.confirmations.service import ConfirmationService
from core.contracts.confirmation import ConfirmationAnswer, ConfirmationBundle
from core.contracts.enums import JobPhase, ModuleId
from core.contracts.job import JobRequest
from core.contracts.result import ConfirmationPrompt, SourceRef
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
    task_repository = app_services["task_repository"]
    assert isinstance(repository, ConfirmationRepository)
    assert isinstance(task_repository, TaskRepository)
    return ConfirmationService(app_services["paths"], repository, task_repository)


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


def _optional_prompt(source_file: Path) -> ConfirmationPrompt:
    return ConfirmationPrompt(
        confirmation_id="mock-optional-1",
        field="optional_field",
        reason="可选人工确认",
        suggested_value="可选值",
        options=["可选值"],
        confidence=0.8,
        blocking=False,
        batch_applicable=True,
        rememberable=True,
        source=SourceRef(source_file=str(source_file)),
    )


def _optional_answer() -> ConfirmationAnswer:
    return ConfirmationAnswer(
        confirmation_id="mock-optional-1",
        value={"choice": "可选值"},
        apply_to_batch=True,
        remember_mapping=True,
    )


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
    assert Path(final_job.confirmation_file or "").name == "confirmation-finalize.json"
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


@pytest.mark.parametrize("value", ["", "4月10日", "2026-02-30", "2026-4-10"])
def test_confirmation_service_rejects_invalid_required_dates(
    qtbot,
    app_services: dict[str, object],
    tmp_path: Path,
    value: str,
) -> None:
    _, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    repository = app_services["confirmation_repository"]
    assert isinstance(repository, ConfirmationRepository)
    repository.save_prompts(
        job_id,
        [
            ConfirmationPrompt(
                confirmation_id="mock-confirm-1",
                field="complaint_date",
                reason="必须明确填写完整日期。",
                suggested_value=None,
                options=[],
                value_type="date",
                confidence=1.0,
                blocking=True,
                batch_applicable=False,
                rememberable=False,
                source=SourceRef(source_file="售后记录.xlsx"),
            )
        ],
    )

    with pytest.raises(ValueError, match="blocking confirmation is empty|YYYY-MM-DD"):
        _confirmation_service(app_services).submit(
            job_id,
            [ConfirmationAnswer(confirmation_id="mock-confirm-1", value=value)],
        )


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

    monkeypatch.setattr(repository, "replace_answers", fail_after_file_write)

    with pytest.raises(RuntimeError, match="simulated answer persistence failure"):
        _confirmation_service(app_services).submit(job_id, [_answer()])

    assert observations == [(True, [])]
    stored_bundle = ConfirmationBundle.model_validate_json(target.read_text(encoding="utf-8"))
    assert stored_bundle.job_id == job_id


def test_confirmation_resubmit_replaces_exact_answer_set(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    repository = app_services["confirmation_repository"]
    assert isinstance(repository, ConfirmationRepository)
    repository.save_prompts(job_id, [_optional_prompt(tmp_path / "confirm.xlsx")])
    confirmation_service = _confirmation_service(app_services)

    confirmation_service.submit(job_id, [_answer(), _optional_answer()])
    bundle_path = confirmation_service.submit(job_id, [_answer()])

    stored = {record["confirmation_id"]: record for record in repository.list_for_job(job_id)}
    assert stored["mock-confirm-1"]["answer"] == _answer().model_dump(mode="json")
    assert stored["mock-optional-1"]["answer"] is None
    bundle = ConfirmationBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    assert bundle.answers == [_answer()]
    assert task_service._states[job_id].state.value == "waiting_confirmation"


def test_confirmation_submit_rejects_non_waiting_job_without_changing_audit(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    confirmation_service = _confirmation_service(app_services)
    bundle_path = confirmation_service.submit(job_id, [_answer()])
    before_file = bundle_path.read_bytes()
    repository = app_services["confirmation_repository"]
    task_repository = app_services["task_repository"]
    assert isinstance(repository, ConfirmationRepository)
    assert isinstance(task_repository, TaskRepository)
    before_records = repository.list_for_job(job_id)
    task_service.finalize(job_id, bundle_path)

    with pytest.raises(InvalidTaskTransition, match="waiting_confirmation"):
        confirmation_service.submit(
            job_id,
            [ConfirmationAnswer(confirmation_id="mock-confirm-1", value="篡改值")],
        )

    assert bundle_path.read_bytes() == before_file
    assert repository.list_for_job(job_id) == before_records
    assert task_repository.get(job_id)["status"] == "running_finalize"


def test_finalize_uses_frozen_confirmation_copy(
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

    source = tmp_path / "confirm-frozen.xlsx"
    source.write_bytes(b"confirmation-source")
    task_service = _task_service(app_services, runner_factory=runner_factory)
    with qtbot.waitSignal(task_service.needs_confirmation, timeout=15_000):
        job_id = task_service.create_and_start(ModuleId.MOISTURE, [source])
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    expected = bundle_path.read_bytes()

    task_service.finalize(job_id, bundle_path)
    final_job = JobRequest.model_validate_json(
        (bundle_path.parent / "job-finalize.json").read_text(encoding="utf-8")
    )
    frozen_path = Path(final_job.confirmation_file or "")
    bundle_path.write_text("{}", encoding="utf-8")

    assert frozen_path.name == "confirmation-finalize.json"
    assert frozen_path.read_bytes() == expected
    assert frozen_path != bundle_path


@pytest.mark.parametrize(
    "mismatch",
    ["db-omission", "bundle-omission", "value", "flags", "duplicate", "unknown"],
)
def test_finalize_rejects_any_bundle_database_answer_map_mismatch(
    qtbot, app_services: dict[str, object], tmp_path: Path, mismatch: str
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    repository = app_services["confirmation_repository"]
    assert isinstance(repository, ConfirmationRepository)
    repository.save_prompts(job_id, [_optional_prompt(tmp_path / "confirm.xlsx")])
    bundle_path = _confirmation_service(app_services).submit(
        job_id, [_answer(), _optional_answer()]
    )
    bundle = ConfirmationBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    if mismatch == "db-omission":
        repository.replace_answers(job_id, [_answer()])
    elif mismatch == "bundle-omission":
        bundle.answers = [_answer()]
    elif mismatch == "value":
        bundle.answers[1].value = "tampered"
    elif mismatch == "flags":
        bundle.answers[1].remember_mapping = False
    elif mismatch == "duplicate":
        bundle.answers.append(_answer())
    else:
        bundle.answers.append(ConfirmationAnswer(confirmation_id="unknown", value="x"))
    if mismatch != "db-omission":
        bundle_path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="answer|duplicate|unknown"):
        task_service.finalize(job_id, bundle_path)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(job_id)["status"] == "waiting_confirmation"


def test_finalize_rejects_bundle_for_a_different_job(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    first_service, first_job_id = _start_waiting_job(
        qtbot, app_services, tmp_path, name="confirm-first.xlsx"
    )
    _, second_job_id = _start_waiting_job(qtbot, app_services, tmp_path, name="confirm-second.xlsx")
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


@pytest.mark.parametrize(
    "tamper",
    [
        "job-id",
        "module",
        "phase",
        "inputs",
        "draft-output",
        "run-mode",
        "ai-enabled",
        "knowledge-scopes",
        "module-config",
        "service-response",
    ],
)
def test_finalize_binds_draft_to_persisted_task_metadata(
    qtbot, app_services: dict[str, object], tmp_path: Path, tamper: str
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    draft_path = bundle_path.parent / "job-draft.json"
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    if tamper == "job-id":
        draft["job_id"] = "different-job-id"
    elif tamper == "module":
        task_repository.database.execute(
            "UPDATE tasks SET module_id = ? WHERE job_id = ?",
            (ModuleId.BOILING.value, job_id),
        )
    elif tamper == "phase":
        draft["phase"] = "finalize"
        draft["parent_job_id"] = job_id
        draft["confirmation_file"] = str(bundle_path)
    elif tamper == "inputs":
        draft["input_files"] = [str(bundle_path)]
    elif tamper == "draft-output":
        draft["output_dir"] = str((bundle_path.parent / "other-output").resolve())
    elif tamper == "run-mode":
        draft["run_mode"] = "batch"
    elif tamper == "ai-enabled":
        draft["ai_enabled"] = True
    elif tamper == "knowledge-scopes":
        draft["allowed_knowledge_scopes"] = ["tampered"]
    elif tamper == "module-config":
        draft["module_config_file"] = str(bundle_path)
    else:
        draft["service_response_file"] = str(bundle_path)
    draft_path.write_text(json.dumps(draft), encoding="utf-8")

    with pytest.raises(ValueError, match="trusted|identity|phase|module|input|output"):
        task_service.finalize(job_id, bundle_path)

    assert task_repository.get(job_id)["status"] == "waiting_confirmation"
    assert not (bundle_path.parent / "job-finalize.json").exists()


def test_finalize_rejects_in_place_snapshot_content_tampering(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    snapshot_path = Path(str(task_repository.list_files(job_id)[0]["snapshot_path"]))
    snapshot_path.write_bytes(b"tampered-after-draft")

    with pytest.raises(ValueError, match="fingerprint"):
        task_service.finalize(job_id, bundle_path)

    assert task_repository.get(job_id)["status"] == "waiting_confirmation"
    assert not (bundle_path.parent / "job-finalize.json").exists()


def test_finalize_rejects_preexisting_output_final_file(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    final_output = bundle_path.parent / "output-final"
    final_output.write_bytes(b"not-a-directory")

    with pytest.raises(ValueError, match="final output.*directory"):
        task_service.finalize(job_id, bundle_path)

    task_repository = app_services["task_repository"]
    assert isinstance(task_repository, TaskRepository)
    assert task_repository.get(job_id)["status"] == "waiting_confirmation"
    assert not (bundle_path.parent / "job-finalize.json").exists()


def test_finalize_allows_preexisting_task_local_output_final_directory(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    final_output = bundle_path.parent / "output-final"
    final_output.mkdir()

    with qtbot.waitSignal(task_service.finished, timeout=15_000) as finished:
        task_service.finalize(job_id, bundle_path)

    assert finished.args[0].status.value == "success"
    assert (final_output / "result.json").is_file()


def test_finalize_rejects_simulated_draft_protocol_link(
    qtbot,
    app_services: dict[str, object],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    draft_path = bundle_path.parent / "job-draft.json"
    original_is_symlink = Path.is_symlink

    def simulated_link(path: Path) -> bool:
        return path == draft_path or original_is_symlink(path)

    monkeypatch.setattr(Path, "is_symlink", simulated_link)

    with pytest.raises(ValueError, match="draft.*link"):
        task_service.finalize(job_id, bundle_path)


@pytest.mark.parametrize("escape", ["task-dir", "draft", "confirmation", "output-final"])
def test_finalize_rejects_real_symlink_escapes(
    qtbot, app_services: dict[str, object], tmp_path: Path, escape: str
) -> None:
    task_service, job_id = _start_waiting_job(qtbot, app_services, tmp_path)
    bundle_path = _confirmation_service(app_services).submit(job_id, [_answer()])
    task_dir = bundle_path.parent
    if escape == "task-dir":
        outside = tmp_path / "external-task"
        shutil.move(str(task_dir), str(outside))
        link = task_dir
        target = outside
        is_directory = True
    elif escape == "output-final":
        outside = tmp_path / "external-output"
        outside.mkdir()
        link = task_dir / "output-final"
        target = outside
        is_directory = True
    else:
        link = task_dir / ("job-draft.json" if escape == "draft" else "confirmation.json")
        target = tmp_path / f"external-{link.name}"
        link.replace(target)
        is_directory = False
    try:
        link.symlink_to(target, target_is_directory=is_directory)
    except OSError as exc:
        pytest.skip(f"Windows symlink privilege unavailable: {exc}")

    active_bundle_path = task_dir / "confirmation.json"
    with pytest.raises(ValueError, match="link|outside|task"):
        task_service.finalize(job_id, active_bundle_path)
