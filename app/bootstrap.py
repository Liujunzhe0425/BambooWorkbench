import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.confirmations.service import ConfirmationService
from core.modules.registry import ModuleRegistry, RegisteredModule
from core.platform.logging import configure_logging
from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.modules import ModuleRepository
from core.storage.repositories.tasks import TaskRepository
from core.storage.settings import SettingsStore
from core.tasks.service import TaskService
from ui.styles.theme import load_stylesheet


@dataclass
class AppContext:
    resource_root: Path
    paths: AppPaths
    database: Database
    settings: SettingsStore
    module_repository: ModuleRepository
    task_repository: TaskRepository
    confirmation_repository: ConfirmationRepository
    registry: ModuleRegistry
    task_service: TaskService
    confirmation_service: ConfirmationService
    scan_results: dict[object, RegisteredModule]
    stylesheet: str
    logger: logging.Logger
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        try:
            cleanup_ok = self.task_service.shutdown()
            if not cleanup_ok:
                self.logger.error("application task cleanup failure before database close")
        finally:
            self.database.close()
            self._closed = True


def resolve_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[1]


def build_context(data_root: Path | None = None, use_mocks: bool = True) -> AppContext:
    resource_root = resolve_resource_root()
    paths = AppPaths.for_root(data_root)
    logger = configure_logging(paths)
    logger.info("application startup data_root=%s", paths.root)
    database = Database.open(paths)
    try:
        database.migrate()
        settings = SettingsStore(database)
        module_repository = ModuleRepository(database)
        task_repository = TaskRepository(database)
        confirmation_repository = ConfirmationRepository(database)
        registry = ModuleRegistry(
            paths.modules,
            resource_root / "mock_modules",
            use_mocks=use_mocks,
            repository=module_repository,
        )
        scan_results = registry.scan()
        logger.info("module scan completed count=%d", len(scan_results))
        task_service = TaskService(
            paths,
            registry,
            task_repository,
            confirmation_repository,
        )
        confirmation_service = ConfirmationService(
            paths,
            confirmation_repository,
            task_repository,
        )
        return AppContext(
            resource_root=resource_root,
            paths=paths,
            database=database,
            settings=settings,
            module_repository=module_repository,
            task_repository=task_repository,
            confirmation_repository=confirmation_repository,
            registry=registry,
            task_service=task_service,
            confirmation_service=confirmation_service,
            scan_results=scan_results,
            stylesheet=load_stylesheet(resource_root),
            logger=logger,
        )
    except Exception:
        database.close()
        raise


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    arguments = sys.argv if argv is None else argv
    application = existing if isinstance(existing, QApplication) else QApplication(arguments)
    application.setApplicationName("竹简工作台")
    application.setOrganizationName("湖大智竹实践团队")
    return application
