# ruff: noqa: E402, I001

from __future__ import annotations

import sys
import json
from pathlib import Path

from PySide6.QtTest import QSignalSpy

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "modules" / "moisture"
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from core.confirmations.service import ConfirmationService
from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.enums import ModuleId
from core.modules.registry import ModuleRegistry
from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.modules import ModuleRepository
from core.storage.repositories.tasks import TaskRepository
from core.tasks.service import TaskService
from app.bootstrap import build_context

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_real_task_service_snapshots_and_registers_formal_outputs(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    paths = AppPaths.for_root(tmp_path / "app-data")
    database = Database.open(paths)
    database.migrate()
    task_repository = TaskRepository(database)
    confirmation_repository = ConfirmationRepository(database)
    registry = ModuleRegistry(
        REPO_ROOT / "modules",
        REPO_ROOT / "mock_modules",
        use_mocks=False,
        repository=ModuleRepository(database),
    )
    registry.scan()
    service = TaskService(
        paths=paths,
        registry=registry,
        task_repository=task_repository,
        confirmation_repository=confirmation_repository,
    )
    source = workbook_factory(tmp_path / "source.xlsx")
    before = source.read_bytes()
    finished = QSignalSpy(service.finished)
    failed = QSignalSpy(service.failed)

    job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    qtbot.waitUntil(lambda: finished.count() + failed.count() == 1, timeout=30_000)

    assert failed.count() == 0
    task = task_repository.get(job_id)
    assert task["status"] == "success"
    assert Path(str(task["result_path"])).is_file()
    outputs = task_repository.list_outputs(job_id)
    assert {Path(str(item["path"])).name for item in outputs} == {
        "moisture_summary.xlsx",
        "analysis_report.md",
    }
    assert all(Path(str(item["path"])).is_file() for item in outputs)
    snapshots = task_repository.list_files(job_id)
    assert len(snapshots) == 1
    assert Path(str(snapshots[0]["snapshot_path"])).read_bytes() == before
    assert source.read_bytes() == before
    assert service.runners == {}
    database.close()


def test_real_task_service_completes_one_batch_year_confirmation(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    paths = AppPaths.for_root(tmp_path / "app-data")
    database = Database.open(paths)
    database.migrate()
    task_repository = TaskRepository(database)
    confirmation_repository = ConfirmationRepository(database)
    registry = ModuleRegistry(
        REPO_ROOT / "modules",
        REPO_ROOT / "mock_modules",
        use_mocks=False,
        repository=ModuleRepository(database),
    )
    registry.scan()
    service = TaskService(
        paths=paths,
        registry=registry,
        task_repository=task_repository,
        confirmation_repository=confirmation_repository,
    )
    sources = [
        workbook_factory(
            tmp_path / f"source-{index}.xlsx",
            departments={"品质": 6 + index * 2},
            arrival_date="4月8日",
            test_date="4月9日",
            total_weight=f"{1000 + index} kg",
        )
        for index in range(2)
    ]
    before = {source: source.read_bytes() for source in sources}
    needs_confirmation = QSignalSpy(service.needs_confirmation)
    finished = QSignalSpy(service.finished)
    failed = QSignalSpy(service.failed)

    job_id = service.create_and_start(ModuleId.MOISTURE, sources)
    qtbot.waitUntil(
        lambda: needs_confirmation.count() + failed.count() == 1,
        timeout=30_000,
    )
    assert failed.count() == 0
    task_dir = paths.tasks / job_id
    draft = json.loads(
        (task_dir / "output-draft" / "result.json").read_text(encoding="utf-8")
    )
    assert draft["status"] == "needs_confirmation"
    assert [item["field"] for item in draft["confirmations"]] == ["default_year"]
    confirmation = ConfirmationService(
        paths,
        confirmation_repository,
        task_repository,
    ).submit(
        job_id,
        [
            ConfirmationAnswer(
                confirmation_id=draft["confirmations"][0]["confirmation_id"],
                value="2026",
                apply_to_batch=True,
                remember_mapping=False,
            )
        ],
    )

    service.finalize(job_id, confirmation)
    qtbot.waitUntil(lambda: finished.count() + failed.count() == 1, timeout=30_000)

    assert failed.count() == 0
    task = task_repository.get(job_id)
    assert task["status"] == "success"
    final = json.loads(
        (task_dir / "output-final" / "result.json").read_text(encoding="utf-8")
    )
    assert final["job_id"] == job_id
    assert final["confirmations"] == []
    assert final["service_requests"] == []
    assert {Path(item["path"]).name for item in final["outputs"]} == {
        "moisture_summary.xlsx",
        "analysis_report.md",
    }
    assert {source: source.read_bytes() for source in sources} == before
    assert service.runners == {}
    database.close()


def test_real_task_service_reuses_draft_ai_request_after_year_confirmation(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    context = build_context(tmp_path / "app-data", use_mocks=False)
    try:
        service = context.task_service
        source = workbook_factory(
            tmp_path / "high-month-day.xlsx",
            departments={"品质": 1},
            moisture_values=(0.56,),
            mass_values=((100, 46.24, 4),),
            material_type="原竹丝",
            arrival_date="4月8日",
            test_date="4月9日",
        )
        before = source.read_bytes()
        needs_confirmation = QSignalSpy(service.needs_confirmation)
        finished = QSignalSpy(service.finished)
        failed = QSignalSpy(service.failed)

        job_id = service.create_and_start(ModuleId.MOISTURE, [source])
        qtbot.waitUntil(
            lambda: needs_confirmation.count() + failed.count() == 1,
            timeout=30_000,
        )

        assert failed.count() == 0
        task_dir = context.paths.tasks / job_id
        draft = json.loads(
            (task_dir / "output-draft" / "result.json").read_text(encoding="utf-8")
        )
        request = next(item for item in draft["service_requests"] if item["service"] == "ai")
        pending = dict(service.pending_confirmations())[job_id]
        assert {prompt.field for prompt in pending.confirmations} == {
            "default_year",
            "AI联网授权：复核水分规则候选摘要",
        }
        answers = [
            ConfirmationAnswer(
                confirmation_id=prompt.confirmation_id,
                value="2026" if prompt.field == "default_year" else "拒绝",
                apply_to_batch=prompt.field == "default_year",
                remember_mapping=False,
            )
            for prompt in pending.confirmations
        ]
        confirmation = context.confirmation_service.submit(job_id, answers)

        service.finalize(job_id, confirmation)
        qtbot.waitUntil(lambda: finished.count() + failed.count() == 1, timeout=30_000)

        assert failed.count() == 0
        final = json.loads(
            (task_dir / "output-final" / "result.json").read_text(encoding="utf-8")
        )
        response = json.loads(
            (task_dir / "protocol" / "service-response.json").read_text(encoding="utf-8")
        )
        assert final["status"] == "success"
        assert response["responses"][0]["request_id"] == request["request_id"]
        assert response["responses"][0]["status"] == "denied"
        assert "SERVICE_RESPONSE_DEGRADED: ai_denied" in final["errors"]
        assert "SERVICE_RESPONSE_DEGRADED: invalid_or_missing" not in final["errors"]
        assert {Path(item["path"]).name for item in final["outputs"]} == {
            "moisture_summary.xlsx",
            "analysis_report.md",
        }
        assert source.read_bytes() == before
        assert service.runners == {}
    finally:
        context.close()
