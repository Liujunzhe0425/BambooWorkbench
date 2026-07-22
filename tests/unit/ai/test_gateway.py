import pytest

from core.ai.audit import ConsentAuditRepository
from core.ai.gateway import AIGateway, ConsentDenied, ConsentRequired, GatewayRequest
from core.ai.providers import AIResponse, MockProvider
from core.security.redaction import RedactionService


def _gateway(database) -> tuple[AIGateway, ConsentAuditRepository]:
    audit = ConsentAuditRepository(database)
    gateway = AIGateway(
        MockProvider(),
        RedactionService(),
        audit,
        clock=lambda: "2026-07-13T09:00:00+08:00",
    )
    return gateway, audit


def test_gateway_returns_preview_before_provider_call(database) -> None:
    gateway, audit = _gateway(database)
    request = GatewayRequest(
        "task-1",
        "after_sales",
        "mock",
        "mock-model",
        {"file": r"D:\客户\a.xlsx"},
    )

    assert gateway.preview(request).payload["file"] == "[LOCAL_PATH]"
    with pytest.raises(ConsentRequired):
        gateway.complete(request, allowed=None)
    assert audit.list_for_task("task-1") == []


def test_allowed_and_denied_decisions_are_audited(database) -> None:
    gateway, audit = _gateway(database)
    request = GatewayRequest(
        "task-1", "after_sales", "mock", "mock-model", {"summary": "异常"}
    )

    assert gateway.complete(request, allowed=True).text.startswith("[模拟AI分析]")
    with pytest.raises(ConsentDenied):
        gateway.complete(request, allowed=False)

    assert [item.allowed for item in audit.list_for_task("task-1")] == [True, False]


def test_gateway_preserves_module_declared_json_output(database) -> None:
    class CapturingProvider:
        def __init__(self) -> None:
            self.requests = []

        def complete(self, request):
            self.requests.append(request)
            return AIResponse('{"schema_version":"1.0"}')

    provider = CapturingProvider()
    gateway = AIGateway(provider, RedactionService(), ConsentAuditRepository(database))

    response = gateway.complete(
        GatewayRequest(
            "task-json",
            "moisture",
            "deepseek",
            "deepseek-chat",
            {"response_schema": {"type": "object"}},
            response_format="json_object",
        ),
        allowed=True,
    )

    assert response.text.startswith("{")
    assert provider.requests[0].response_format == "json_object"
    assert "仅返回一个合法 JSON 对象" in provider.requests[0].system
