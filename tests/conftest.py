from collections.abc import Iterator
from pathlib import Path

import pytest

from core.modules.registry import ModuleRegistry
from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.modules import ModuleRepository
from core.storage.repositories.tasks import TaskRepository


@pytest.fixture
def app_services(tmp_path: Path) -> Iterator[dict[str, object]]:
    paths = AppPaths.for_root(tmp_path / "app-data")
    database = Database.open(paths)
    database.migrate()
    task_repository = TaskRepository(database)
    confirmation_repository = ConfirmationRepository(database)
    registry = ModuleRegistry(
        paths.modules,
        Path(__file__).parents[1] / "mock_modules",
        use_mocks=True,
        repository=ModuleRepository(database),
    )
    registry.scan()
    try:
        yield {
            "paths": paths,
            "registry": registry,
            "task_repository": task_repository,
            "confirmation_repository": confirmation_repository,
        }
    finally:
        database.close()


@pytest.fixture
def app_context(tmp_path: Path) -> Iterator[object]:
    from app.bootstrap import build_context

    context = build_context(tmp_path / "desktop-data", use_mocks=True)
    try:
        yield context
    finally:
        context.close()
