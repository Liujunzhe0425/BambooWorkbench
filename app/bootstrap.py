import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication

from core.ai.audit import ConsentAuditRepository
from core.ai.gateway import AIGateway
from core.ai.providers import (
    AIProvider,
    DeepSeekProvider,
    MockProvider,
    OpenAICompatibleProvider,
    UnavailableProvider,
)
from core.confirmations.service import ConfirmationService
from core.knowledge.learning import LearningEvidenceRepository
from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository
from core.modules.management_service import ModuleManagementService
from core.modules.registry import ModuleRegistry, RegisteredModule
from core.platform.installation import complete_fresh_installation, prepare_installation
from core.platform.logging import close_logging, configure_logging
from core.platform.paths import AppPaths
from core.security.credentials import CredentialStore, KeyringCredentialStore
from core.security.redaction import RedactionService
from core.services.orchestrator import ServiceOrchestrator
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.credential_state import CredentialStateRepository
from core.storage.repositories.modules import ModuleRepository
from core.storage.repositories.monthly import MonthlyRepository
from core.storage.repositories.output_roots import OutputRootRepository
from core.storage.repositories.tasks import TaskRepository
from core.storage.settings import SettingsStore
from core.tasks.monthly_service import MonthlyRollupService
from core.tasks.output_recovery import OutputRecoveryService
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
    learning_repository: LearningEvidenceRepository
    monthly_repository: MonthlyRepository
    output_root_repository: OutputRootRepository
    credential_state_repository: CredentialStateRepository
    credential_store: CredentialStore
    ai_gateway: AIGateway
    service_orchestrator: ServiceOrchestrator
    registry: ModuleRegistry
    task_service: TaskService
    module_management_service: ModuleManagementService
    confirmation_service: ConfirmationService
    scan_results: dict[object, RegisteredModule]
    stylesheet: str
    logger: logging.Logger
    _closed: bool = field(default=False, init=False, repr=False)

    def close(self) -> None:
        if self._closed:
            return
        try:
            management_ok = self.module_management_service.shutdown()
            cleanup_ok = self.task_service.shutdown()
            if not cleanup_ok or not management_ok:
                self.logger.error("application task cleanup failure before database close")
        finally:
            self.database.close()
            close_logging(self.logger, self.paths)
            self._closed = True

    def reload_ai_configuration(self) -> None:
        provider, provider_id, model = _configured_ai_provider(
            self.settings,
            self.credential_store,
            self.logger,
        )
        self.ai_gateway.set_provider(provider)
        self.service_orchestrator.provider_id = provider_id
        self.service_orchestrator.model = model


def resolve_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS).resolve()
    return Path(__file__).resolve().parents[1]


def resolve_real_modules_root(resource_root: Path, paths: AppPaths) -> Path:
    """Prefer modules shipped with the application, then local installed modules."""
    bundled_modules = resource_root / "modules"
    return bundled_modules if bundled_modules.is_dir() else paths.modules


def build_context(data_root: Path | None = None, use_mocks: bool = False) -> AppContext:
    resource_root = resolve_resource_root()
    paths = AppPaths.for_root(data_root)
    installation = prepare_installation(paths)
    logger = configure_logging(paths)
    logger.info("application startup data_root=%s", paths.root)
    database = Database.open(paths)
    try:
        database.migrate()
        settings = SettingsStore(database)
        credential_store = KeyringCredentialStore()
        # Explicit roots are development/test sandboxes.  Only a normal frozen
        # startup is allowed to clear machine credentials for a new install.
        complete_fresh_installation(
            paths,
            installation,
            settings,
            credential_store,
            clear_credentials=data_root is None,
        )
        module_repository = ModuleRepository(database)
        task_repository = TaskRepository(database)
        confirmation_repository = ConfirmationRepository(database)
        consent_audit_repository = ConsentAuditRepository(database)
        knowledge_repository = KnowledgeRepository(database)
        learning_repository = LearningEvidenceRepository(database)
        monthly_repository = MonthlyRepository(database)
        output_root_repository = OutputRootRepository(database, paths)
        if not output_root_repository.list_all():
            output_root_repository.restore_from_registry()
        configured_output = settings.get("output_dir", "") or ""
        if configured_output:
            output_root_repository.set_current(
                Path(configured_output),
                is_default=Path(configured_output).resolve() == paths.output,
            )
        elif not output_root_repository.list_all():
            output_root_repository.initialize_default()
        else:
            settings.set(
                "output_dir", str(output_root_repository.current()["path"])
            )
        output_recovery_service = OutputRecoveryService(
            paths,
            task_repository,
            monthly_repository,
            output_root_repository,
        )
        recovery_summary = output_recovery_service.scan()
        logger.info("output manifest scan completed summary=%s", recovery_summary)
        credential_state_repository = CredentialStateRepository(database)
        _seed_framework_knowledge(knowledge_repository)
        ai_provider, provider_id, model = _configured_ai_provider(
            settings,
            credential_store,
            logger,
        )
        ai_gateway = AIGateway(
            ai_provider,
            RedactionService(),
            consent_audit_repository,
        )
        service_orchestrator = ServiceOrchestrator(
            knowledge_repository,
            ai_gateway,
            provider_id=provider_id,
            model=model,
        )
        registry = ModuleRegistry(
            resolve_real_modules_root(resource_root, paths),
            resource_root / "mock_modules",
            use_mocks=use_mocks,
            repository=module_repository,
        )
        scan_results = registry.scan()
        logger.info("module scan completed count=%d", len(scan_results))
        module_management_service = ModuleManagementService(paths, registry)
        monthly_rollup_service = MonthlyRollupService(
            paths,
            registry,
            task_repository,
            confirmation_repository,
            monthly_repository,
            learning_repository,
            output_root_repository,
        )
        task_service = TaskService(
            paths,
            registry,
            task_repository,
            confirmation_repository,
            service_orchestrator=service_orchestrator,
            settings=settings,
            module_management_service=module_management_service,
            monthly_rollup_service=monthly_rollup_service,
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
            learning_repository=learning_repository,
            monthly_repository=monthly_repository,
            output_root_repository=output_root_repository,
            credential_state_repository=credential_state_repository,
            credential_store=credential_store,
            ai_gateway=ai_gateway,
            service_orchestrator=service_orchestrator,
            registry=registry,
            task_service=task_service,
            module_management_service=module_management_service,
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


def _configured_ai_provider(
    settings: SettingsStore,
    credential_store: CredentialStore,
    logger: logging.Logger,
) -> tuple[AIProvider, str, str]:
    provider_id = settings.get("ai_provider", "mock") or "mock"
    model = settings.get("ai_model", "mock-model") or "mock-model"
    if provider_id == "mock":
        return MockProvider(), provider_id, model
    try:
        api_key = credential_store.get_secret(provider_id)
    except Exception as error:
        logger.warning(
            "AI credential lookup failed provider_id=%s error_type=%s",
            provider_id,
            type(error).__name__,
        )
        api_key = None
    if not api_key:
        return (
            UnavailableProvider(provider_id, "尚未安全保存所选 AI 提供商的 API 密钥。"),
            provider_id,
            model,
        )
    base_url = settings.get("ai_base_url", "") or ""
    if provider_id == "deepseek":
        return (
            DeepSeekProvider(api_key, base_url or "https://api.deepseek.com"),
            provider_id,
            model,
        )
    if provider_id == "openai-compatible":
        return (
            OpenAICompatibleProvider(base_url or "https://api.openai.com/v1", api_key),
            provider_id,
            model,
        )
    return (
        UnavailableProvider(provider_id, "不支持的 AI 提供商配置。"),
        provider_id,
        model,
    )


def create_application(argv: list[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    arguments = sys.argv if argv is None else argv
    application = existing if isinstance(existing, QApplication) else QApplication(arguments)
    application.setApplicationName("竹简工作台")
    application.setOrganizationName("湖南大学智创未来团队")
    application.setStyle("Fusion")
    application.setFont(QFont("Microsoft YaHei UI", 10))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#E8EFE7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#294D3C"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#FFFDF8"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F4F7F1"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFDF8"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#294D3C"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#294D3C"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#F4F1E2"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#294D3C"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2F7D62"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFDF8"))
    application.setPalette(palette)
    application.setWindowIcon(
        QIcon(str(resolve_resource_root() / "logo" / "team-logo.png"))
    )
    return application
