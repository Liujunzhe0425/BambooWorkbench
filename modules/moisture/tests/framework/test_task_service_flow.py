# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
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

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _service(tmp_path: Path):
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
    return paths, database, task_repository, confirmation_repository, service


def test_real_task_service_snapshots_and_registers_formal_outputs(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    paths, database, task_repository, _, service = _service(tmp_path)
    try:
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
    finally:
        database.close()


def test_real_task_service_year_confirmation_does_not_request_ai(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    paths, database, task_repository, confirmation_repository, service = _service(tmp_path)
    try:
        source = workbook_factory(
            tmp_path / "source.xlsx",
            moisture_values=(0.50,),
            mass_values=((100, 50, 0),),
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
        task_dir = paths.tasks / job_id
        draft = json.loads((task_dir / "output-draft" / "result.json").read_text(encoding="utf-8"))
        assert [item["field"] for item in draft["confirmations"]] == ["default_year"]
        assert not any(item["service"] == "ai" for item in draft["service_requests"])

        confirmation = ConfirmationService(paths, confirmation_repository, task_repository).submit(
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
        final = json.loads((task_dir / "output-final" / "result.json").read_text(encoding="utf-8"))
        assert final["job_id"] == job_id
        assert final["status"] == "success"
        assert final["confirmations"] == []
        assert final["service_requests"] == []
        assert not any("ai_" in error.lower() for error in final["errors"])
        assert {Path(item["path"]).name for item in final["outputs"]} == {
            "moisture_summary.xlsx",
            "analysis_report.md",
        }
        assert source.read_bytes() == before
        assert service.runners == {}
    finally:
        database.close()
