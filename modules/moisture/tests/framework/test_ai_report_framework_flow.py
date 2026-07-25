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
from core.confirmations.service import ConfirmationService
from core.contracts.confirmation import ConfirmationAnswer
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
    )
    return paths, database, tasks, confirmations, registry, task_service


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
    paths, database, tasks, confirmations, registry, service = _context(tmp_path, provider)
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

        waiting = QSignalSpy(service.needs_confirmation)
        failed = QSignalSpy(service.failed)
        allowed_job = service.create_and_start(
            ModuleId.MOISTURE,
            [summary],
            module_config=config,
        )
        _wait(qtbot, waiting, failed)
        task_dir = paths.tasks / allowed_job
        draft_config = json.loads(
            (task_dir / "module-config.json").read_text(encoding="utf-8")
        )
        rule_snapshot = draft_config["rule_selection"]
        assert set(rule_snapshot) == {"version", "sha256"}
        draft = json.loads((task_dir / "output-draft" / "result.json").read_text(encoding="utf-8"))
        request_id = draft["service_requests"][0]["request_id"]
        records = confirmations.list_for_job(allowed_job)
        consent_id = str(records[0]["confirmation_id"])
        bundle = ConfirmationService(paths, confirmations, tasks).submit(
            allowed_job,
            [ConfirmationAnswer(confirmation_id=consent_id, value="允许")],
        )
        finished = QSignalSpy(service.finished)
        failed = QSignalSpy(service.failed)
        service.finalize(allowed_job, bundle)
        _wait(qtbot, finished, failed)

        final_config = json.loads(
            (task_dir / "module-config.json").read_text(encoding="utf-8")
        )
        assert final_config["rule_selection"] == rule_snapshot
        final = json.loads((task_dir / "output-final" / "result.json").read_text(encoding="utf-8"))
        assert final["job_id"] == allowed_job
        assert final["confirmations"] == []
        assert final["service_requests"] == []
        assert {Path(item["path"]).name for item in final["outputs"]} == {
            "ai_analysis_report.md",
            "ai_analysis_result.json",
        }
        protocol = json.loads(
            (task_dir / "protocol" / "service-response.json").read_text(encoding="utf-8")
        )
        assert protocol["responses"][0]["request_id"] == request_id
        assert provider.call_count == 1
        assert summary.read_bytes() == before

        waiting = QSignalSpy(service.needs_confirmation)
        failed = QSignalSpy(service.failed)
        denied_job = service.create_and_start(
            ModuleId.MOISTURE,
            [summary],
            module_config=config,
        )
        _wait(qtbot, waiting, failed)
        denied_dir = paths.tasks / denied_job
        records = confirmations.list_for_job(denied_job)
        bundle = ConfirmationService(paths, confirmations, tasks).submit(
            denied_job,
            [
                ConfirmationAnswer(
                    confirmation_id=str(records[0]["confirmation_id"]),
                    value="拒绝",
                )
            ],
        )
        finished = QSignalSpy(service.finished)
        failed = QSignalSpy(service.failed)
        service.finalize(denied_job, bundle)
        _wait(qtbot, finished, failed)
        denied = json.loads(
            (denied_dir / "output-final" / "result.json").read_text(encoding="utf-8")
        )
        assert {Path(item["path"]).name for item in denied["outputs"]} == {
            "ai_analysis_result.json"
        }
        assert not (denied_dir / "output-final" / "ai_analysis_report.md").exists()
        assert provider.call_count == 1
        assert summary.read_bytes() == before
    finally:
        service.shutdown()
        database.close()


def test_real_management_service_imports_and_lists_module_data(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    provider = _ValidReportProvider()
    paths, database, tasks, _, registry, task_service = _context(tmp_path, provider)
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
    paths, database, tasks, confirmations, _, service = _context(tmp_path, provider)
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
        for mode, expected_status in (
            ("error", "error"),
            ("timeout", "timeout"),
            ("invalid", "invalid_response"),
        ):
            provider.mode = mode
            waiting = QSignalSpy(service.needs_confirmation)
            failed = QSignalSpy(service.failed)
            job_id = service.create_and_start(
                ModuleId.MOISTURE,
                [summary],
                module_config=config,
            )
            _wait(qtbot, waiting, failed)
            records = confirmations.list_for_job(job_id)
            bundle = ConfirmationService(paths, confirmations, tasks).submit(
                job_id,
                [
                    ConfirmationAnswer(
                        confirmation_id=str(records[0]["confirmation_id"]),
                        value="允许",
                    )
                ],
            )
            finished = QSignalSpy(service.finished)
            failed = QSignalSpy(service.failed)
            service.finalize(job_id, bundle)
            _wait(qtbot, finished, failed)
            final_dir = paths.tasks / job_id / "output-final"
            result = json.loads((final_dir / "ai_analysis_result.json").read_text(encoding="utf-8"))
            assert result["status"] == expected_status
            assert result["report_file"] is None
            assert not (final_dir / "ai_analysis_report.md").exists()
            assert summary.read_bytes() == before
    finally:
        service.shutdown()
        database.close()
