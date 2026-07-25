from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent.cli import _create_sample_workbook  # noqa: E402
from framework_ai_helpers import analysis_for_case  # noqa: E402

from core.ai.audit import ConsentAuditRepository  # noqa: E402
from core.ai.gateway import AIGateway  # noqa: E402
from core.ai.providers import AIRequest, AIResponse  # noqa: E402
from core.confirmations.service import ConfirmationService  # noqa: E402
from core.contracts.confirmation import ConfirmationAnswer  # noqa: E402
from core.contracts.enums import ModuleId  # noqa: E402
from core.contracts.manifest import ModuleManifest  # noqa: E402
from core.knowledge.repository import KnowledgeRepository  # noqa: E402
from core.modules.registry import (  # noqa: E402
    ModuleRegistry,
    RegisteredModule,
)
from core.platform.paths import AppPaths  # noqa: E402
from core.security.redaction import RedactionService  # noqa: E402
from core.services.orchestrator import ServiceOrchestrator  # noqa: E402
from core.storage.database import Database  # noqa: E402
from core.storage.repositories.confirmations import ConfirmationRepository  # noqa: E402
from core.storage.repositories.tasks import TaskRepository  # noqa: E402
from core.tasks.models import InvalidTaskTransition  # noqa: E402
from core.tasks.service import TaskService  # noqa: E402


class ContractProvider:
    provider_id = "contract-test"

    def __init__(self) -> None:
        self.calls: list[AIRequest] = []

    def complete(self, request: AIRequest) -> AIResponse:
        self.calls.append(request)
        payload = json.loads(request.prompt)
        return AIResponse(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "batch_id": payload["batch_id"],
                    "analyses": [
                        analysis_for_case(case) for case in payload["cases"]
                    ],
                },
                ensure_ascii=False,
            )
        )


def _real_registry(tmp_path: Path) -> ModuleRegistry:
    manifest = ModuleManifest.model_validate_json(
        (MODULE_ROOT / "module.json").read_text(encoding="utf-8")
    )
    registry = ModuleRegistry(
        REPO_ROOT / "modules",
        tmp_path / "unused-mocks",
        use_mocks=False,
    )
    registry._modules[ModuleId.AFTER_SALES] = RegisteredModule(
        manifest=manifest,
        path=MODULE_ROOT,
        is_mock=False,
        health="healthy",
    )
    return registry


def test_real_task_service_calls_provider_once_and_finalize_reuses_response(
    qtbot, tmp_path: Path
) -> None:
    paths = AppPaths.for_root(tmp_path / "task-service")
    paths.ensure()
    database = Database.open(paths)
    database.migrate()
    task_repository = TaskRepository(database)
    confirmation_repository = ConfirmationRepository(database)
    provider = ContractProvider()
    gateway = AIGateway(
        provider,
        RedactionService(),
        ConsentAuditRepository(database),
    )
    orchestrator = ServiceOrchestrator(
        KnowledgeRepository(database),
        gateway,
        provider_id=provider.provider_id,
        model="contract-model",
    )
    service = TaskService(
        paths=paths,
        registry=_real_registry(tmp_path),
        task_repository=task_repository,
        confirmation_repository=confirmation_repository,
        service_orchestrator=orchestrator,
        job_id_factory=lambda: "after-sales-real-flow",
    )
    source = tmp_path / "真实TaskService脱敏样表.xlsx"
    _create_sample_workbook(
        source,
        customer="脱敏任务客户",
        brand_text="桃花江竹地板",
        date_text="2026-07-25",
        feedback="定制板开片尺寸错误，现场无法安装。",
        solution="补发产品，企业售后成本1000元，正在处理中。",
    )

    with pytest.raises(ValueError, match="必须先完成框架 AI 配置"):
        service.create_and_start(
            ModuleId.AFTER_SALES,
            [source],
            ai_consent_granted=False,
        )
    assert not paths.tasks.exists() or not list(paths.tasks.iterdir())

    with qtbot.waitSignal(service.needs_confirmation, timeout=60_000) as pending:
        job_id = service.create_and_start(
            ModuleId.AFTER_SALES,
            [source],
            ai_consent_granted=True,
        )

    assert job_id == "after-sales-real-flow"
    assert len(provider.calls) == 1
    assert provider.calls[0].response_format == "json_object"
    prompts = pending.args[1].confirmations
    assert {prompt.field for prompt in prompts} >= {"售后费用", "责任工厂", "投诉类型"}
    response_path = paths.tasks / job_id / "protocol" / "service-response.json"
    assert response_path.is_file()
    assert "api_key" not in response_path.read_text(encoding="utf-8").casefold()

    confirmation_service = ConfirmationService(
        paths,
        confirmation_repository,
        task_repository,
    )
    bundle_path = confirmation_service.submit(
        job_id,
        [
            ConfirmationAnswer(
                confirmation_id=prompt.confirmation_id,
                value=prompt.suggested_value,
            )
            for prompt in prompts
        ],
    )
    with qtbot.waitSignal(service.finished, timeout=60_000) as finished:
        service.finalize(job_id, bundle_path)

    assert finished.args[0].status.value == "success"
    assert len(provider.calls) == 1
    final_result = json.loads(
        (paths.tasks / job_id / "output-final" / "result.json").read_text(
            encoding="utf-8"
        )
    )
    assert final_result["service_requests"] == []
    with pytest.raises(InvalidTaskTransition):
        service.finalize(job_id, bundle_path)
    assert len(provider.calls) == 1
    assert service.shutdown()
    database.close()
