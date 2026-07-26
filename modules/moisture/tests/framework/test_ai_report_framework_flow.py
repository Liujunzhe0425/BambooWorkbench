# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from PySide6.QtTest import QSignalSpy

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "modules" / "moisture"
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from core.ai.audit import ConsentAuditRepository
from core.ai.gateway import AIGateway
from core.ai.providers import AIResponse, ProviderResponseError
from core.contracts.enums import ModuleId
from core.contracts.management import ModuleManagementOperation
from core.knowledge.repository import KnowledgeRepository
from core.modules.management_service import ModuleManagementService
from core.modules.registry import ModuleRegistry
from core.platform.paths import AppPaths
from core.security.redaction import RedactionService
from core.services.orchestrator import ServiceOrchestrator
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.modules import ModuleRepository
from core.storage.repositories.tasks import TaskRepository
from core.storage.settings import SettingsStore
from core.tasks.service import TaskService

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


class _ValidReportProvider:
    provider_id = "test-valid"

    def __init__(self) -> None:
        self.call_count = 0
        self.mode = "valid"

    def complete(self, request) -> AIResponse:
        self.call_count += 1
        if self.mode == "error":
            raise ProviderResponseError("synthetic provider error")
        if self.mode == "timeout":
            raise httpx.TimeoutException("synthetic timeout")
        if self.mode == "invalid":
            return AIResponse("not-json")
        payload = json.loads(request.prompt)
        return AIResponse(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "context_hash": payload["context_hash"],
                    "overall_summary": "本期确定性数据总体稳定。",
                    "historical_comparison": "本次未选择历史资料。",
                    "review_batches": [],
                    "possible_causes": ["未发现需要模型推断的明确原因。"],
                    "recommendations": ["继续按现有频次进行人工复核。"],
                    "evidence_refs": [],
                    "disclaimer": "本报告仅作辅助分析，不构成正式质量结论。",
                },
                ensure_ascii=False,
            )
        )


def _context(tmp_path: Path, provider: _ValidReportProvider):
    paths = AppPaths.for_root(tmp_path / "app-data")
    database = Database.open(paths)
    database.migrate()
    tasks = TaskRepository(database)
    confirmations = ConfirmationRepository(database)
    settings = SettingsStore(database)
    registry = ModuleRegistry(
        REPO_ROOT / "modules",
        REPO_ROOT / "mock_modules",
        use_mocks=False,
        repository=ModuleRepository(database),
    )
    registry.scan()
    gateway = AIGateway(
        provider,
        RedactionService(),
        ConsentAuditRepository(database),
    )
    orchestrator = ServiceOrchestrator(
        KnowledgeRepository(database),
        gateway,
        provider_id=provider.provider_id,
        model="test-model",
    )
    task_service = TaskService(
        paths=paths,
        registry=registry,
        task_repository=tasks,
        confirmation_repository=confirmations,
        service_orchestrator=orchestrator,
        settings=settings,
    )
    return paths, database, tasks, confirmations, registry, settings, task_service


def _wait(qtbot, success: QSignalSpy, failure: QSignalSpy) -> None:
    qtbot.waitUntil(lambda: success.count() + failure.count() == 1, timeout=45_000)
    assert failure.count() == 0, failure.at(0) if failure.count() else None


def _make_summary(
    qtbot,
    tmp_path: Path,
    workbook_factory,
    tasks: TaskRepository,
    service: TaskService,
) -> Path:
    source = workbook_factory(
        tmp_path / "raw.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        supplier="脱敏供应商",
        arrival_date="2026-07-01",
        test_date="2026-07-02",
    )
    finished = QSignalSpy(service.finished)
    failed = QSignalSpy(service.failed)
    job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    _wait(qtbot, finished, failed)
    return next(
        Path(str(item["path"]))
        for item in tasks.list_outputs(job_id)
        if Path(str(item["path"])).name == "moisture_summary.xlsx"
    )


def test_real_task_service_ai_report_allow_and_deny(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    provider = _ValidReportProvider()
    paths, database, tasks, confirmations, registry, settings, service = _context(
        tmp_path, provider
    )
    try:
        contract = registry.get(ModuleId.MOISTURE).manifest.management_contract
        assert contract is not None
        assert contract.schema_version == "1.1"
        summary = _make_summary(qtbot, tmp_path, workbook_factory, tasks, service)
        before = summary.read_bytes()
        config = {
            "schema_version": "1.0",
            "operation": "ai_report",
            "inputs": [{"role": "current_summary", "input_index": 0}],
            "history_ids": [],
            "experience_selections": [],
            "question": "请概括本期情况并提出人工复核建议。",
        }

        settings.set("ai_network_enabled", "true")
        waiting = QSignalSpy(service.needs_confirmation)
        finished = QSignalSpy(service.finished)
        failed = QSignalSpy(service.failed)
        allowed_job = service.create_and_start(
            ModuleId.MOISTURE,
            [summary],
            module_config=config,
        )
        _wait(qtbot, finished, failed)
        assert waiting.count() == 0
        task_dir = paths.tasks / allowed_job
        draft_config = json.loads(
            (task_dir / "module-config.json").read_text(encoding="utf-8")
        )
        rule_snapshot = draft_config["rule_selection"]
        assert set(rule_snapshot) == {"version", "sha256"}
        assert confirmations.list_for_job(allowed_job) == []

        final_config = json.loads(
            (task_dir / "module-config.json").read_text(encoding="utf-8")
        )
        assert final_config["rule_selection"] == rule_snapshot
        result_path = Path(str(tasks.get(allowed_job)["result_path"]))
        final = json.loads(result_path.read_text(encoding="utf-8"))
        assert final["job_id"] == allowed_job
        assert final["confirmations"] == []
        assert final["service_requests"] == []
        assert final["monthly_snapshot"] is None
        assert {Path(item["path"]).name for item in final["outputs"]} == {
            "ai_analysis_report.md",
            "ai_analysis_result.json",
        }
        protocol = json.loads(
            (task_dir / "protocol" / "service-response.json").read_text(encoding="utf-8")
        )
        assert protocol["responses"][0]["status"] == "ok"
        assert protocol["responses"][0]["request_id"]
        assert provider.call_count == 1
        allowed_task = tasks.get(allowed_job)
        assert allowed_task["period_year"] is None
        assert allowed_task["period_month"] is None
        assert summary.read_bytes() == before

        settings.set("ai_network_enabled", "false")
        waiting = QSignalSpy(service.needs_confirmation)
        finished = QSignalSpy(service.finished)
        failed = QSignalSpy(service.failed)
        denied_job = service.create_and_start(
            ModuleId.MOISTURE,
            [summary],
            module_config=config,
        )
        _wait(qtbot, finished, failed)
        assert waiting.count() == 0
        denied_dir = paths.tasks / denied_job
        assert confirmations.list_for_job(denied_job) == []
        denied_result_path = Path(str(tasks.get(denied_job)["result_path"]))
        denied = json.loads(denied_result_path.read_text(encoding="utf-8"))
        assert denied["monthly_snapshot"] is None
        assert {Path(item["path"]).name for item in denied["outputs"]} == {
            "ai_analysis_result.json"
        }
        assert not (denied_result_path.parent / "ai_analysis_report.md").exists()
        denied_protocol = json.loads(
            (denied_dir / "protocol" / "service-response.json").read_text(
                encoding="utf-8"
            )
        )
        assert denied_protocol["responses"][0]["status"] == "denied"
        assert provider.call_count == 1
        denied_task = tasks.get(denied_job)
        assert denied_task["period_year"] is None
        assert denied_task["period_month"] is None
        assert summary.read_bytes() == before
    finally:
        service.shutdown()
        database.close()


def test_real_management_service_imports_and_lists_module_data(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    provider = _ValidReportProvider()
    paths, database, tasks, _, registry, _, task_service = _context(tmp_path, provider)
    management = ModuleManagementService(paths, registry)
    try:
        summary = _make_summary(qtbot, tmp_path, workbook_factory, tasks, task_service)
        completed = QSignalSpy(management.completed)
        failed = QSignalSpy(management.failed)

        management.run(
            ModuleId.MOISTURE,
            ModuleManagementOperation.IMPORT_HISTORY_SUMMARY,
            input_file=summary,
        )
        _wait(qtbot, completed, failed)
        imported_id = completed.at(0)[1].imported_history_id
        assert imported_id

        completed = QSignalSpy(management.completed)
        failed = QSignalSpy(management.failed)
        management.run(
            ModuleId.MOISTURE,
            ModuleManagementOperation.LIST_HISTORY_SUMMARIES,
        )
        _wait(qtbot, completed, failed)
        assert completed.at(0)[1].history_items[0].history_id == imported_id

        completed = QSignalSpy(management.completed)
        failed = QSignalSpy(management.failed)
        management.run(
            ModuleId.MOISTURE,
            ModuleManagementOperation.LIST_APPROVED_EXPERIENCES,
        )
        _wait(qtbot, completed, failed)
        assert completed.at(0)[1].experience_items
    finally:
        management.shutdown()
        task_service.shutdown()
        database.close()


def test_real_task_service_provider_failures_do_not_create_fake_report(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    provider = _ValidReportProvider()
    paths, database, tasks, confirmations, _, settings, service = _context(
        tmp_path, provider
    )
    try:
        summary = _make_summary(qtbot, tmp_path, workbook_factory, tasks, service)
        before = summary.read_bytes()
        config = {
            "schema_version": "1.0",
            "operation": "ai_report",
            "inputs": [{"role": "current_summary", "input_index": 0}],
            "history_ids": [],
            "experience_selections": [],
            "question": "请生成辅助分析。",
        }
        settings.set("ai_network_enabled", "true")
        for expected_call_count, (mode, expected_status) in enumerate(
            (
            ("error", "error"),
            ("timeout", "timeout"),
            ("invalid", "invalid_response"),
            ),
            start=1,
        ):
            provider.mode = mode
            waiting = QSignalSpy(service.needs_confirmation)
            finished = QSignalSpy(service.finished)
            failed = QSignalSpy(service.failed)
            job_id = service.create_and_start(
                ModuleId.MOISTURE,
                [summary],
                module_config=config,
            )
            _wait(qtbot, finished, failed)
            assert waiting.count() == 0
            assert confirmations.list_for_job(job_id) == []
            final_dir = Path(str(tasks.get(job_id)["result_path"])).parent
            module_result = json.loads(
                (final_dir / "result.json").read_text(encoding="utf-8")
            )
            assert module_result["monthly_snapshot"] is None
            result = json.loads((final_dir / "ai_analysis_result.json").read_text(encoding="utf-8"))
            assert result["status"] == expected_status
            assert result["report_file"] is None
            assert not (final_dir / "ai_analysis_report.md").exists()
            assert provider.call_count == expected_call_count
            task = tasks.get(job_id)
            assert task["period_year"] is None
            assert task["period_month"] is None
            assert summary.read_bytes() == before
    finally:
        service.shutdown()
        database.close()
