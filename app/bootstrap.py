import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtWidgets import QApplication

from core.ai.audit import ConsentAuditRepository
from core.ai.gateway import AIGateway
from core.ai.providers import MockProvider
from core.confirmations.service import ConfirmationService
from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository
from core.modules.registry import ModuleRegistry, RegisteredModule
from core.platform.logging import close_logging, configure_logging
from core.platform.paths import AppPaths
from core.security.credentials import CredentialStore, KeyringCredentialStore
from core.security.redaction import RedactionService
from core.services.orchestrator import ServiceOrchestrator
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
    consent_audit_repository: ConsentAuditRepository
    knowledge_repository: KnowledgeRepository
    credential_store: CredentialStore
    ai_gateway: AIGateway
    service_orchestrator: ServiceOrchestrator
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
            close_logging(self.logger, self.paths)
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
        consent_audit_repository = ConsentAuditRepository(database)
        knowledge_repository = KnowledgeRepository(database)
        _seed_framework_knowledge(knowledge_repository)
        credential_store = KeyringCredentialStore()
        ai_gateway = AIGateway(
            MockProvider(),
            RedactionService(),
            consent_audit_repository,
        )
        service_orchestrator = ServiceOrchestrator(
            knowledge_repository,
            ai_gateway,
            provider_id="mock",
            model=settings.get("ai_model", "mock-model") or "mock-model",
        )
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
            service_orchestrator=service_orchestrator,
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
            consent_audit_repository=consent_audit_repository,
            knowledge_repository=knowledge_repository,
            credential_store=credential_store,
            ai_gateway=ai_gateway,
            service_orchestrator=service_orchestrator,
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


def _seed_framework_knowledge(repository: KnowledgeRepository) -> None:
    if repository.list_records():
        return
    records = (
        KnowledgeRecord(
            "framework-rule-priority",
            "shared",
            "品质判断知识优先级",
            "客户确认的正式规则优先于本次人工确认、历史案例和模型通用知识。",
            KnowledgeSourceKind.CONFIRMED_RULE,
            True,
        ),
        KnowledgeRecord(
            "framework-moisture-example",
            "moisture",
            "竹丝水分模拟知识",
            "水分异常阈值必须由模块规则和客户确认标准提供，框架不自行判断。",
            KnowledgeSourceKind.HISTORICAL_EXAMPLE,
            True,
        ),
        KnowledgeRecord(
            "framework-boiling-example",
            "boiling",
            "水煮实验模拟知识",
            "水煮实验结论由业务模块生成，边界问题进入人工确认。",
            KnowledgeSourceKind.HISTORICAL_EXAMPLE,
            True,
        ),
        KnowledgeRecord(
            "framework-after-sales-example",
            "after_sales",
            "售后分析模拟知识",
            "售后问题分类和建议必须保留来源追溯并允许人工复核。",
            KnowledgeSourceKind.HISTORICAL_EXAMPLE,
            True,
        ),
    )
    for record in records:
        repository.add(record)


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    arguments = sys.argv if argv is None else argv
    application = existing if isinstance(existing, QApplication) else QApplication(arguments)
    application.setApplicationName("竹简工作台")
    application.setOrganizationName("湖大智竹实践团队")
    return application
