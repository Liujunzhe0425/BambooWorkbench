import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from core.ai.audit import ConsentAuditRepository, ConsentDecision
from core.ai.providers import AIProvider, AIRequest, AIResponse
from core.security.redaction import RedactionPreview, RedactionService


class ConsentRequired(RuntimeError):
    pass


class ConsentDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class GatewayRequest:
    task_id: str
    module_id: str
    provider_id: str
    model: str
    payload: dict[str, object]


class AIGateway:
    def __init__(
        self,
        provider: AIProvider,
        redactor: RedactionService,
        audit_repository: ConsentAuditRepository,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.provider = provider
        self.redactor = redactor
        self.audit_repository = audit_repository
        self.clock = clock or (lambda: datetime.now().astimezone().isoformat())

    def preview(self, request: GatewayRequest) -> RedactionPreview:
        return self.redactor.redact(request.payload)

    def complete(self, request: GatewayRequest, allowed: bool | None) -> AIResponse:
        preview = self.preview(request)
        if allowed is None:
            raise ConsentRequired("AI request requires an explicit consent decision")
        self.audit_repository.record(
            ConsentDecision(
                task_id=request.task_id,
                module_id=request.module_id,
                provider_id=request.provider_id,
                allowed=allowed,
                data_categories=preview.categories,
                decided_at=self.clock(),
            )
        )
        if not allowed:
            raise ConsentDenied("user declined the AI request")
        prompt = json.dumps(preview.payload, ensure_ascii=False, sort_keys=True)
        return self.provider.complete(
            AIRequest(
                model=request.model,
                system="你是品质数据分析助手。规则和人工确认高于模型通用知识。",
                prompt=prompt,
            )
        )
