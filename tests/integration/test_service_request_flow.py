import json
from dataclasses import replace
from pathlib import Path

import pytest

from core.ai.audit import ConsentAuditRepository
from core.ai.gateway import AIGateway, ConsentRequired
from core.ai.providers import MockProvider, ProviderConfigurationError
from core.confirmations.service import ConfirmationService
from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.enums import ModuleId
from core.contracts.job import JobRequest
from core.contracts.service_request import ServiceRequest
from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository
from core.security.redaction import RedactionService
from core.services.orchestrator import KnowledgeScopeDenied, ServiceOrchestrator
from core.storage.settings import SettingsStore
from core.tasks.service import TaskService


def _orchestrator(database) -> tuple[ServiceOrchestrator, ConsentAuditRepository]:
    knowledge = KnowledgeRepository(database)
    knowledge.add(
        KnowledgeRecord(
            "rule-1",
            "shared",
            "异常处理规则",
            "客户确认后才可形成正式结论",
            KnowledgeSourceKind.CONFIRMED_RULE,
            True,
        )
    )
    audit = ConsentAuditRepository(database)
    gateway = AIGateway(MockProvider(), RedactionService(), audit)
    return ServiceOrchestrator(knowledge, gateway), audit


def _requests() -> list[ServiceRequest]:
    return [
        ServiceRequest(
            request_id="knowledge-1",
            service="knowledge",
            scope="moisture",
            purpose="检索规则",
            payload={"query": "异常"},
            requires_user_consent=False,
        ),
        ServiceRequest(
            request_id="ai-1",
            service="ai",
            purpose="生成分析",
            payload={"file": r"D:\客户\水分.xlsx", "summary": "异常"},
            requires_user_consent=True,
        ),
    ]


def test_resolves_requests_in_order_and_writes_task_local_response(
    database, tmp_path: Path
) -> None:
    orchestrator, audit = _orchestrator(database)
    task_dir = tmp_path / "task-1"
    task_dir.mkdir()

    path = orchestrator.resolve(
        task_id="task-1",
        module_id="moisture",
        allowed_namespaces={"shared", "moisture"},
        requests=_requests(),
        ai_consent={"ai-1": True},
        task_dir=task_dir,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [item["request_id"] for item in payload["responses"]] == [
        "knowledge-1",
        "ai-1",
    ]
    assert path == task_dir / "protocol" / "service-response.json"
    assert payload["responses"][0]["items"][0]["record_id"] == "rule-1"
    assert "D:\\客户" not in path.read_text(encoding="utf-8")
    assert audit.list_for_task("task-1")[0].allowed is True


def test_denied_ai_is_a_response_not_a_task_crash(database, tmp_path: Path) -> None:
    orchestrator, audit = _orchestrator(database)
    task_dir = tmp_path / "task-denied"
    task_dir.mkdir()

    path = orchestrator.resolve(
        "task-denied",
        "moisture",
        {"shared", "moisture"},
        [_requests()[1]],
        {"ai-1": False},
        task_dir,
    )

    response = json.loads(path.read_text(encoding="utf-8"))["responses"][0]
    assert response["status"] == "denied"
    assert audit.list_for_task("task-denied")[0].allowed is False


def test_missing_consent_and_forbidden_namespace_are_typed(database, tmp_path: Path) -> None:
    orchestrator, _audit = _orchestrator(database)
    task_dir = tmp_path / "task-errors"
    task_dir.mkdir()

    with pytest.raises(ConsentRequired):
        orchestrator.resolve(
            "task-errors",
            "moisture",
            {"shared", "moisture"},
            [_requests()[1]],
            {},
            task_dir,
        )

    forbidden = _requests()[0].model_copy(update={"scope": "after_sales"})
    with pytest.raises(KnowledgeScopeDenied):
        orchestrator.resolve(
            "task-errors",
            "moisture",
            {"shared", "moisture"},
            [forbidden],
            {},
            task_dir,
        )


def test_unavailable_ai_provider_is_written_as_degraded_response(
    database, tmp_path: Path
) -> None:
    class Unavailable:
        def complete(self, _request):
            raise ProviderConfigurationError("sensitive local provider detail")

    knowledge = KnowledgeRepository(database)
    audit = ConsentAuditRepository(database)
    gateway = AIGateway(Unavailable(), RedactionService(), audit)
    orchestrator = ServiceOrchestrator(knowledge, gateway, provider_id="deepseek")
    task_dir = tmp_path / "task-provider-error"
    task_dir.mkdir()

    path = orchestrator.resolve(
        "task-provider-error",
        "moisture",
        {"shared", "moisture"},
        [_requests()[1]],
        {"ai-1": True},
        task_dir,
    )

    response = json.loads(path.read_text(encoding="utf-8"))["responses"][0]
    assert response == {
        "request_id": "ai-1",
        "service": "ai",
        "status": "error",
        "text": None,
        "error": "provider_error",
    }
    assert "sensitive" not in path.read_text(encoding="utf-8")

def _task_service(
    app_services: dict[str, object], settings: SettingsStore | None = None
) -> TaskService:
    orchestrator, _audit = _orchestrator(app_services["database"])
    return TaskService(
        paths=app_services["paths"],
        registry=app_services["registry"],
        task_repository=app_services["task_repository"],
        confirmation_repository=app_services["confirmation_repository"],
        service_orchestrator=orchestrator,
        settings=settings,
    )


def _confirmation_service(app_services: dict[str, object]) -> ConfirmationService:
    return ConfirmationService(
        app_services["paths"],
        app_services["confirmation_repository"],
        app_services["task_repository"],
    )


def test_ai_service_consent_finalizes_with_task_local_response(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "ai.xlsx"
    source.write_bytes(b"ai-service")
    settings = SettingsStore(app_services["database"])
    settings.set("ai_network_enabled", "true")
    service = _task_service(app_services, settings)

    with qtbot.waitSignal(service.needs_confirmation, timeout=15_000) as pending:
        job_id = service.create_and_start(ModuleId.AFTER_SALES, [source])

    prompt = pending.args[1].confirmations[0]
    assert prompt.confirmation_id == "mock-ai-review"
    bundle_path = _confirmation_service(app_services).submit(
        job_id,
        [ConfirmationAnswer(confirmation_id=prompt.confirmation_id, value="人工值")],
    )

    with qtbot.waitSignal(service.finished, timeout=15_000) as finished:
        service.finalize(job_id, bundle_path)

    assert finished.args[0].status.value == "success"
    task_dir = app_services["paths"].tasks / job_id
    final_job = JobRequest.model_validate_json(
        (task_dir / "job-finalize.json").read_text(encoding="utf-8")
    )
    response_path = Path(final_job.service_response_file or "")
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response_path == task_dir / "protocol" / "service-response.json"
    assert response["responses"][0]["status"] == "ok"
    assert final_job.ai_enabled is True


def test_denied_ai_still_finalizes_local_module(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "ai-denied.xlsx"
    source.write_bytes(b"ai-denied")
    service = _task_service(app_services)

    with qtbot.waitSignal(service.needs_confirmation, timeout=15_000) as pending:
        job_id = service.create_and_start(ModuleId.AFTER_SALES, [source])
    prompt = pending.args[1].confirmations[0]
    bundle_path = _confirmation_service(app_services).submit(
        job_id,
        [ConfirmationAnswer(confirmation_id=prompt.confirmation_id, value="人工值")],
    )

    with qtbot.waitSignal(service.finished, timeout=15_000):
        service.finalize(job_id, bundle_path)

    task_dir = app_services["paths"].tasks / job_id
    response = json.loads(
        (task_dir / "protocol" / "service-response.json").read_text(encoding="utf-8")
    )
    assert response["responses"][0]["status"] == "denied"
    assert app_services["task_repository"].get(job_id)["status"] == "success"


def test_knowledge_only_request_auto_finalizes_without_user_confirmation(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    source = tmp_path / "knowledge.xlsx"
    source.write_bytes(b"knowledge")
    service = _task_service(app_services)

    with qtbot.waitSignal(service.finished, timeout=15_000) as finished:
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])

    assert finished.args[0].status.value == "success"
    task_dir = app_services["paths"].tasks / job_id
    final_job = JobRequest.model_validate_json(
        (task_dir / "job-finalize.json").read_text(encoding="utf-8")
    )
    assert final_job.service_response_file is not None
    assert app_services["confirmation_repository"].list_for_job(job_id) == []


def test_required_framework_ai_runs_before_business_confirmation(
    qtbot, app_services: dict[str, object], tmp_path: Path
) -> None:
    registry = app_services["registry"]
    module = registry.get(ModuleId.AFTER_SALES)
    registry._modules[ModuleId.AFTER_SALES] = replace(
        module,
        manifest=type(module.manifest).model_validate(
            {
                **module.manifest.model_dump(mode="python"),
                "framework_ai": {
                    "required": True,
                    "setup_page": "module",
                    "service_before_confirmation": True,
                },
            }
        ),
    )
    source = tmp_path / "ai-required.xlsx"
    source.write_bytes(b"ai-required")
    service = _task_service(app_services)

    with qtbot.waitSignal(service.needs_confirmation, timeout=20_000) as pending:
        job_id = service.create_and_start(
            ModuleId.AFTER_SALES,
            [source],
            ai_consent_granted=True,
        )

    prompts = pending.args[1].confirmations
    assert [prompt.confirmation_id for prompt in prompts] == ["mock-ai-review"]
    task_dir = app_services["paths"].tasks / job_id
    rebound = JobRequest.model_validate_json(
        (task_dir / "job-draft.json").read_text(encoding="utf-8")
    )
    assert rebound.ai_enabled is True
    assert rebound.service_response_file is not None

    bundle_path = _confirmation_service(app_services).submit(
        job_id,
        [ConfirmationAnswer(confirmation_id="mock-ai-review", value="人工值")],
    )
    with qtbot.waitSignal(service.finished, timeout=20_000):
        service.finalize(job_id, bundle_path)

    final_job = JobRequest.model_validate_json(
        (task_dir / "job-finalize.json").read_text(encoding="utf-8")
    )
    assert final_job.ai_enabled is True
    assert final_job.service_response_file == rebound.service_response_file
