# BambooWorkbench AI Gateway and Knowledge Services Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable shared AI and knowledge services that modules can request without receiving API credentials, while preserving a fully local mock path.

**Architecture:** Modules describe knowledge or AI needs through the frozen service-request contract. The framework validates module scope, searches enabled local knowledge metadata first, redacts outbound content, records consent, and invokes either a deterministic mock provider or an OpenAI-compatible HTTP provider. Results are written to a task-local service response and returned to the module only during finalize.

**Tech Stack:** Python 3.12, Pydantic 2 contracts from Plan 1, sqlite3 repositories from Plan 2, keyring, httpx, PySide6, pytest, pytest-qt.

## Global Constraints

- Complete Plans 1 and 2 first.
- Customer-confirmed rules and current human confirmation outrank historical examples and model knowledge.
- The default provider is offline `mock`; no real network request occurs without configured credentials and explicit per-request consent.
- API keys are stored only through the credential backend and never appear in settings JSON, SQLite, logs, task files, exceptions, or tests.
- Modules never receive credentials or call providers directly.
- The empty-framework release implements metadata and deterministic mock retrieval, not production vector search or automatic rule learning.
- Use TDD and commit after every independently testable task.

---

## File Map

| Path | Responsibility |
|---|---|
| `core/security/credentials.py` | Credential backend protocol and keyring adapter |
| `core/security/redaction.py` | Deterministic outbound-data redaction |
| `core/ai/providers.py` | Mock and OpenAI-compatible providers |
| `core/ai/gateway.py` | Configuration, consent, redaction, provider dispatch, audit |
| `core/knowledge/models.py` | Knowledge namespaces, source priority, and records |
| `core/knowledge/repository.py` | Knowledge metadata and deterministic mock search |
| `core/services/orchestrator.py` | Resolve module service requests and write response file |
| `ui/pages/settings_page.py` | Provider configuration without exposing stored keys |
| `ui/pages/knowledge_page.py` | Import, enable/disable, and mock-search metadata |
| `tests/unit/ai/` | Security and provider tests |
| `tests/unit/knowledge/` | Namespace and search tests |
| `tests/integration/test_service_request_flow.py` | End-to-end service/finalize flow |

### Task 1: Implement an injectable credential store

**Files:**
- Create: `core/security/__init__.py`
- Create: `core/security/credentials.py`
- Test: `tests/unit/ai/test_credentials.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing credential round-trip test**

```python
from core.security.credentials import InMemoryCredentialStore


def test_memory_store_never_exposes_values_when_listed():
    store = InMemoryCredentialStore()
    store.set_secret("openai-compatible", "sk-test")
    assert store.has_secret("openai-compatible") is True
    assert store.get_secret("openai-compatible") == "sk-test"
    assert "sk-test" not in repr(store)
```

- [ ] **Step 2: Run it and verify the missing-module failure**

Run: `python -m pytest tests/unit/ai/test_credentials.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'core.security'`.

- [ ] **Step 3: Add the protocol, memory backend, and keyring adapter**

```python
from typing import Protocol
import keyring

SERVICE_NAME = "BambooWorkbench"


class CredentialStore(Protocol):
    def set_secret(self, provider_id: str, value: str) -> None: ...
    def get_secret(self, provider_id: str) -> str | None: ...
    def has_secret(self, provider_id: str) -> bool: ...
    def delete_secret(self, provider_id: str) -> None: ...


class InMemoryCredentialStore:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set_secret(self, provider_id: str, value: str) -> None:
        self._values[provider_id] = value

    def get_secret(self, provider_id: str) -> str | None:
        return self._values.get(provider_id)

    def has_secret(self, provider_id: str) -> bool:
        return provider_id in self._values

    def delete_secret(self, provider_id: str) -> None:
        self._values.pop(provider_id, None)

    def __repr__(self) -> str:
        return "InMemoryCredentialStore(<redacted>)"


class KeyringCredentialStore:
    def set_secret(self, provider_id: str, value: str) -> None:
        keyring.set_password(SERVICE_NAME, provider_id, value)

    def get_secret(self, provider_id: str) -> str | None:
        return keyring.get_password(SERVICE_NAME, provider_id)

    def has_secret(self, provider_id: str) -> bool:
        return self.get_secret(provider_id) is not None

    def delete_secret(self, provider_id: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, provider_id)
        except keyring.errors.PasswordDeleteError:
            pass
```

Add `keyring>=25,<26` to runtime dependencies.

- [ ] **Step 4: Run the focused test**

Run: `python -m pytest tests/unit/ai/test_credentials.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add core/security pyproject.toml tests/unit/ai/test_credentials.py
git commit -m "feat: add secure credential storage boundary"
```

### Task 2: Implement deterministic outbound redaction

**Files:**
- Create: `core/security/redaction.py`
- Test: `tests/unit/ai/test_redaction.py`

- [ ] **Step 1: Write failing tests for file paths and sensitive fields**

```python
from core.security.redaction import RedactionService


def test_redacts_windows_paths_and_named_sensitive_values():
    source = {
        "operator_name": "张三",
        "file": r"D:\客户资料\售后.xlsx",
        "summary": "批次 B-2026-01 需要复核",
    }
    result = RedactionService().redact(source)
    assert result.payload["operator_name"] == "[REDACTED]"
    assert result.payload["file"] == "[LOCAL_PATH]"
    assert result.payload["summary"] == "批次 B-2026-01 需要复核"
    assert set(result.categories) == {"personal_field", "local_path"}
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/ai/test_redaction.py -q`
Expected: FAIL because `RedactionService` does not exist.

- [ ] **Step 3: Implement recursive redaction with a typed preview**

```python
from dataclasses import dataclass
import re
from typing import Any

SENSITIVE_KEYS = {"operator_name", "phone", "email", "customer_name", "api_key"}
WINDOWS_PATH = re.compile(r"^[A-Za-z]:\\")


@dataclass(frozen=True)
class RedactionPreview:
    payload: Any
    categories: tuple[str, ...]


class RedactionService:
    def redact(self, value: Any) -> RedactionPreview:
        categories: set[str] = set()

        def visit(item: Any, key: str | None = None) -> Any:
            if key in SENSITIVE_KEYS:
                categories.add("personal_field")
                return "[REDACTED]"
            if isinstance(item, str) and WINDOWS_PATH.match(item):
                categories.add("local_path")
                return "[LOCAL_PATH]"
            if isinstance(item, dict):
                return {k: visit(v, k) for k, v in item.items()}
            if isinstance(item, list):
                return [visit(v) for v in item]
            return item

        return RedactionPreview(visit(value), tuple(sorted(categories)))
```

- [ ] **Step 4: Run focused tests and commit**

Run: `python -m pytest tests/unit/ai/test_redaction.py -q`
Expected: PASS.

```powershell
git add core/security/redaction.py tests/unit/ai/test_redaction.py
git commit -m "feat: add outbound data redaction"
```

### Task 3: Add AI consent audit persistence

**Files:**
- Modify: `core/storage/database.py`
- Create: `core/ai/audit.py`
- Test: `tests/unit/ai/test_consent_audit.py`

- [ ] **Step 1: Write the failing repository test**

```python
from core.ai.audit import ConsentAuditRepository, ConsentDecision


def test_records_decision_without_request_body(database):
    repo = ConsentAuditRepository(database)
    repo.record(ConsentDecision(
        task_id="task-1", module_id="after_sales", provider_id="mock",
        allowed=False, data_categories=("local_path",), decided_at="2026-07-13T09:00:00+08:00",
    ))
    row = repo.list_for_task("task-1")[0]
    assert row.allowed is False
    assert not hasattr(row, "request_body")
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/ai/test_consent_audit.py -q`
Expected: FAIL because the audit repository is missing.

- [ ] **Step 3: Add migration `003_ai_consent_audit`**

```sql
CREATE TABLE ai_consent_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    module_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    data_categories_json TEXT NOT NULL,
    decided_at TEXT NOT NULL
);
CREATE INDEX idx_ai_consent_task ON ai_consent_audit(task_id);
```

- [ ] **Step 4: Implement the immutable record and repository**

```python
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class ConsentDecision:
    task_id: str
    module_id: str
    provider_id: str
    allowed: bool
    data_categories: tuple[str, ...]
    decided_at: str


class ConsentAuditRepository:
    def __init__(self, database) -> None:
        self.database = database

    def record(self, decision: ConsentDecision) -> None:
        self.database.execute(
            "INSERT INTO ai_consent_audit(task_id,module_id,provider_id,allowed,data_categories_json,decided_at) VALUES(?,?,?,?,?,?)",
            (decision.task_id, decision.module_id, decision.provider_id, int(decision.allowed),
             json.dumps(decision.data_categories, ensure_ascii=False), decision.decided_at),
        )

    def list_for_task(self, task_id: str) -> list[ConsentDecision]:
        rows = self.database.query_all("SELECT * FROM ai_consent_audit WHERE task_id=? ORDER BY id", (task_id,))
        return [ConsentDecision(r["task_id"], r["module_id"], r["provider_id"], bool(r["allowed"]),
                                tuple(json.loads(r["data_categories_json"])), r["decided_at"]) for r in rows]
```

- [ ] **Step 5: Run and commit**

Run: `python -m pytest tests/unit/ai/test_consent_audit.py -q`
Expected: PASS.

```powershell
git add core/storage/database.py core/ai/audit.py tests/unit/ai/test_consent_audit.py
git commit -m "feat: persist AI consent audit metadata"
```

### Task 4: Implement mock and OpenAI-compatible providers

**Files:**
- Create: `core/ai/__init__.py`
- Create: `core/ai/providers.py`
- Test: `tests/unit/ai/test_providers.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing provider tests using `httpx.MockTransport`**

```python
import httpx
from core.ai.providers import AIRequest, MockProvider, OpenAICompatibleProvider


def test_mock_provider_is_deterministic():
    request = AIRequest(model="mock-model", system="quality", prompt="分析异常")
    assert MockProvider().complete(request).text == "[模拟AI分析] 分析异常"


def test_openai_compatible_provider_uses_bearer_without_leaking_it():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json={"choices": [{"message": {"content": "建议复核"}}]})
    provider = OpenAICompatibleProvider("https://example.invalid/v1", "secret", httpx.Client(transport=httpx.MockTransport(handler)))
    response = provider.complete(AIRequest(model="model-a", system="quality", prompt="分析"))
    assert response.text == "建议复核"
    assert "secret" not in repr(provider)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/ai/test_providers.py -q`
Expected: FAIL because provider types are missing.

- [ ] **Step 3: Implement the narrow provider boundary**

```python
from dataclasses import dataclass
from typing import Protocol
import httpx


@dataclass(frozen=True)
class AIRequest:
    model: str
    system: str
    prompt: str


@dataclass(frozen=True)
class AIResponse:
    text: str


class AIProvider(Protocol):
    def complete(self, request: AIRequest) -> AIResponse: ...


class MockProvider:
    def complete(self, request: AIRequest) -> AIResponse:
        return AIResponse(f"[模拟AI分析] {request.prompt}")


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, api_key: str, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.client = client or httpx.Client(timeout=30)

    def complete(self, request: AIRequest) -> AIResponse:
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": request.model, "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ]},
        )
        response.raise_for_status()
        return AIResponse(response.json()["choices"][0]["message"]["content"])

    def __repr__(self) -> str:
        return f"OpenAICompatibleProvider(base_url={self.base_url!r}, api_key=<redacted>)"
```

Add `httpx>=0.28,<1` to runtime dependencies.

- [ ] **Step 4: Run and commit**

Run: `python -m pytest tests/unit/ai/test_providers.py -q`
Expected: PASS with no network access.

```powershell
git add core/ai pyproject.toml tests/unit/ai/test_providers.py
git commit -m "feat: add mock and OpenAI-compatible providers"
```

### Task 5: Implement knowledge namespaces and priority-aware mock search

**Files:**
- Create: `core/knowledge/__init__.py`
- Create: `core/knowledge/models.py`
- Create: `core/knowledge/repository.py`
- Modify: `core/storage/database.py`
- Test: `tests/unit/knowledge/test_repository.py`

- [ ] **Step 1: Write the failing namespace and priority test**

```python
from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository


def test_confirmed_rules_rank_before_examples(database):
    repo = KnowledgeRepository(database)
    repo.add(KnowledgeRecord("rule-1", "shared", "水分规则", "以客户确认阈值为准", KnowledgeSourceKind.CONFIRMED_RULE, True))
    repo.add(KnowledgeRecord("example-1", "shared", "水分案例", "历史样本", KnowledgeSourceKind.HISTORICAL_EXAMPLE, True))
    results = repo.search("shared", "水分")
    assert [item.record_id for item in results] == ["rule-1", "example-1"]
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/knowledge/test_repository.py -q`
Expected: FAIL because knowledge types are absent.

- [ ] **Step 3: Add migration `004_knowledge_records`**

```sql
CREATE TABLE knowledge_records (
    record_id TEXT PRIMARY KEY,
    namespace TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    source_path TEXT
);
CREATE INDEX idx_knowledge_namespace ON knowledge_records(namespace, enabled);
```

- [ ] **Step 4: Implement explicit namespace validation and ordering**

```python
from dataclasses import dataclass
from enum import StrEnum

ALLOWED_NAMESPACES = {"shared", "moisture", "boiling", "after_sales"}


class KnowledgeSourceKind(StrEnum):
    CONFIRMED_RULE = "confirmed_rule"
    CURRENT_CONFIRMATION = "current_confirmation"
    HISTORICAL_EXAMPLE = "historical_example"
    MODEL_KNOWLEDGE = "model_knowledge"


SOURCE_PRIORITY = {
    KnowledgeSourceKind.CONFIRMED_RULE: 0,
    KnowledgeSourceKind.CURRENT_CONFIRMATION: 1,
    KnowledgeSourceKind.HISTORICAL_EXAMPLE: 2,
    KnowledgeSourceKind.MODEL_KNOWLEDGE: 3,
}


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    namespace: str
    title: str
    content: str
    source_kind: KnowledgeSourceKind
    enabled: bool
    source_path: str | None = None

    def __post_init__(self) -> None:
        if self.namespace not in ALLOWED_NAMESPACES:
            raise ValueError(f"unsupported knowledge namespace: {self.namespace}")
```

```python
from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind, SOURCE_PRIORITY


class KnowledgeRepository:
    def __init__(self, database) -> None:
        self.database = database

    def add(self, record: KnowledgeRecord) -> None:
        self.database.execute(
            "INSERT OR REPLACE INTO knowledge_records VALUES(?,?,?,?,?,?,?)",
            (record.record_id, record.namespace, record.title, record.content,
             record.source_kind.value, int(record.enabled), record.source_path),
        )

    def search(self, namespace: str, query: str) -> list[KnowledgeRecord]:
        rows = self.database.query_all(
            "SELECT * FROM knowledge_records WHERE enabled=1 AND namespace IN ('shared', ?) AND (title LIKE ? OR content LIKE ?)",
            (namespace, f"%{query}%", f"%{query}%"),
        )
        records = [KnowledgeRecord(r["record_id"], r["namespace"], r["title"], r["content"],
                                   KnowledgeSourceKind(r["source_kind"]), bool(r["enabled"]), r["source_path"]) for r in rows]
        return sorted(records, key=lambda item: (SOURCE_PRIORITY[item.source_kind], item.record_id))
```

- [ ] **Step 5: Run and commit**

Run: `python -m pytest tests/unit/knowledge/test_repository.py -q`
Expected: PASS.

```powershell
git add core/knowledge core/storage/database.py tests/unit/knowledge/test_repository.py
git commit -m "feat: add priority-aware mock knowledge search"
```

### Task 6: Build the consent-gated AI gateway

**Files:**
- Create: `core/ai/gateway.py`
- Test: `tests/unit/ai/test_gateway.py`

- [ ] **Step 1: Write failing tests for refusal and allowed mock use**

```python
import pytest
from core.ai.gateway import AIGateway, ConsentRequired, GatewayRequest
from core.ai.providers import MockProvider
from core.security.redaction import RedactionService


def test_gateway_returns_preview_before_provider_call(audit_repository):
    gateway = AIGateway(MockProvider(), RedactionService(), audit_repository)
    request = GatewayRequest("task-1", "after_sales", "mock", "mock-model", {"file": r"D:\客户\a.xlsx"})
    preview = gateway.preview(request)
    assert preview.payload["file"] == "[LOCAL_PATH]"
    with pytest.raises(ConsentRequired):
        gateway.complete(request, allowed=None)


def test_allowed_mock_call_records_consent(audit_repository):
    gateway = AIGateway(MockProvider(), RedactionService(), audit_repository)
    request = GatewayRequest("task-1", "after_sales", "mock", "mock-model", {"summary": "异常"})
    assert gateway.complete(request, allowed=True).text.startswith("[模拟AI分析]")
    assert audit_repository.list_for_task("task-1")[0].allowed is True
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/ai/test_gateway.py -q`
Expected: FAIL because `AIGateway` is absent.

- [ ] **Step 3: Implement preview, consent enforcement, and metadata-only audit**

```python
from dataclasses import dataclass
from datetime import datetime
import json
from core.ai.audit import ConsentDecision
from core.ai.providers import AIRequest, AIResponse


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
    payload: dict


class AIGateway:
    def __init__(self, provider, redactor, audit_repository, clock=lambda: datetime.now().astimezone().isoformat()) -> None:
        self.provider = provider
        self.redactor = redactor
        self.audit_repository = audit_repository
        self.clock = clock

    def preview(self, request: GatewayRequest):
        return self.redactor.redact(request.payload)

    def complete(self, request: GatewayRequest, allowed: bool | None) -> AIResponse:
        preview = self.preview(request)
        if allowed is None:
            raise ConsentRequired("AI request requires explicit user consent")
        self.audit_repository.record(ConsentDecision(
            request.task_id, request.module_id, request.provider_id, allowed,
            preview.categories, self.clock(),
        ))
        if not allowed:
            raise ConsentDenied("user declined the AI request")
        prompt = json.dumps(preview.payload, ensure_ascii=False, sort_keys=True)
        return self.provider.complete(AIRequest(request.model, "你是品质数据分析助手。", prompt))
```

- [ ] **Step 4: Run and commit**

Run: `python -m pytest tests/unit/ai/test_gateway.py -q`
Expected: PASS.

```powershell
git add core/ai/gateway.py tests/unit/ai/test_gateway.py
git commit -m "feat: gate AI requests with redaction and consent"
```

### Task 7: Resolve module service requests and produce a finalize input

**Files:**
- Create: `core/services/__init__.py`
- Create: `core/services/orchestrator.py`
- Modify: `core/tasks/service.py`
- Test: `tests/integration/test_service_request_flow.py`

- [ ] **Step 1: Write the failing mixed knowledge-and-AI flow test**

```python
import json
from core.services.orchestrator import ServiceOrchestrator


def test_resolves_requests_in_order_and_writes_task_local_response(service_fixture):
    orchestrator = ServiceOrchestrator(**service_fixture.dependencies)
    path = orchestrator.resolve(
        task_id="task-1", module_id="moisture",
        allowed_namespaces={"shared", "moisture"},
        requests=service_fixture.requests,
        ai_consent={"ai-1": True},
        task_dir=service_fixture.task_dir,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert [item["request_id"] for item in payload["responses"]] == ["knowledge-1", "ai-1"]
    assert path == service_fixture.task_dir / "protocol" / "service-response.json"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/integration/test_service_request_flow.py -q`
Expected: FAIL because the orchestrator is missing.

- [ ] **Step 3: Implement scope checking, deterministic response order, and atomic write**

```python
import json
from pathlib import Path
from core.ai.gateway import GatewayRequest


class KnowledgeScopeDenied(RuntimeError):
    pass


class ServiceOrchestrator:
    def __init__(self, knowledge_repository, ai_gateway, provider_id: str = "mock", model: str = "mock-model") -> None:
        self.knowledge_repository = knowledge_repository
        self.ai_gateway = ai_gateway
        self.provider_id = provider_id
        self.model = model

    def resolve(self, task_id: str, module_id: str, allowed_namespaces: set[str], requests: list[dict],
                ai_consent: dict[str, bool], task_dir: Path) -> Path:
        responses: list[dict] = []
        for item in requests:
            if item["service"] == "knowledge":
                namespace = item["scope"]
                if namespace not in allowed_namespaces:
                    raise KnowledgeScopeDenied(namespace)
                hits = self.knowledge_repository.search(namespace, str(item["payload"]["query"]))
                responses.append({"request_id": item["request_id"], "status": "ok",
                                  "items": [hit.__dict__ for hit in hits]})
            elif item["service"] == "ai":
                response = self.ai_gateway.complete(
                    GatewayRequest(task_id, module_id, self.provider_id, self.model, item["payload"]),
                    ai_consent.get(item["request_id"]),
                )
                responses.append({"request_id": item["request_id"], "status": "ok", "text": response.text})
            else:
                responses.append({"request_id": item["request_id"], "status": "unsupported"})
        target = task_dir / "protocol" / "service-response.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps({"responses": responses}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        temporary.replace(target)
        return target
```

Update `TaskService.finalize()` to call `ServiceOrchestrator.resolve()` before creating the finalize `JobRequest`, then set its `service_response_file` to the returned path. Do not put service resolution in the UI.

- [ ] **Step 4: Run the integration test and the Plan 2 confirmation tests**

Run: `python -m pytest tests/integration/test_service_request_flow.py tests/integration/test_confirmation_flow.py -q`
Expected: PASS; finalized jobs reference `protocol/service-response.json`.

- [ ] **Step 5: Commit**

```powershell
git add core/services core/tasks/service.py tests/integration/test_service_request_flow.py
git commit -m "feat: resolve shared services before module finalize"
```

### Task 8: Connect real settings and knowledge pages to the services

**Files:**
- Modify: `ui/pages/settings_page.py`
- Modify: `ui/pages/knowledge_page.py`
- Modify: `app/bootstrap.py`
- Test: `tests/ui/test_ai_knowledge_pages.py`

- [ ] **Step 1: Write failing UI tests for secret handling and mock search**

```python
def test_settings_saves_key_to_credential_store_only(qtbot, settings_page, credential_store, settings_repository):
    qtbot.addWidget(settings_page)
    settings_page.provider_combo.setCurrentText("OpenAI兼容")
    settings_page.api_key_edit.setText("secret")
    qtbot.mouseClick(settings_page.save_button, settings_page.save_button.mouseButton())
    assert credential_store.get_secret("openai-compatible") == "secret"
    assert "secret" not in str(settings_repository.get_all())


def test_knowledge_page_searches_selected_namespace(qtbot, knowledge_page):
    qtbot.addWidget(knowledge_page)
    knowledge_page.namespace_combo.setCurrentText("公共知识")
    knowledge_page.query_edit.setText("水分")
    qtbot.mouseClick(knowledge_page.search_button, knowledge_page.search_button.mouseButton())
    assert knowledge_page.results.count() >= 1
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/ui/test_ai_knowledge_pages.py -q`
Expected: FAIL because pages are still diagnostics-only shells.

- [ ] **Step 3: Implement the smallest service-backed page behavior**

`SettingsPage` must expose `provider_combo`, `base_url_edit`, `model_edit`, `api_key_edit`, `network_checkbox`, `save_button`, and `credential_status_label`. Saving writes provider/base URL/model/network state through `SettingsRepository`, writes a non-empty key through `CredentialStore`, clears the key field, and displays only `已安全保存`.

`KnowledgePage` must expose `namespace_combo`, `query_edit`, `search_button`, `results`, `import_button`, and `enabled_checkbox`. It calls `KnowledgeRepository.search()` using the namespace mapping `公共知识→shared`, `竹丝水分→moisture`, `水煮实验→boiling`, `售后分析→after_sales`. Import stores metadata and a copied local source path; it does not create embeddings.

In `app/bootstrap.py`, construct `KeyringCredentialStore`, `RedactionService`, `KnowledgeRepository`, `ConsentAuditRepository`, and `AIGateway(MockProvider(), ...)`, inject them into pages and `TaskService`, and keep `mock` as the startup provider.

- [ ] **Step 4: Run UI and service suites**

Run: `python -m pytest tests/ui/test_ai_knowledge_pages.py tests/integration/test_service_request_flow.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add ui/pages/settings_page.py ui/pages/knowledge_page.py app/bootstrap.py tests/ui/test_ai_knowledge_pages.py
git commit -m "feat: connect AI settings and knowledge management UI"
```

## Plan 3 Completion Gate

Run:

```powershell
python -m pytest tests/unit/ai tests/unit/knowledge tests/integration/test_service_request_flow.py tests/integration/test_confirmation_flow.py tests/ui/test_ai_knowledge_pages.py -q
python -m ruff check core/security core/ai core/knowledge core/services ui/pages/settings_page.py ui/pages/knowledge_page.py
```

Expected:

- all tests pass without real network traffic;
- no plaintext secret appears under `data/`, `logs/`, task directories, SQLite dumps, or captured test output;
- denied consent, missing credentials, empty knowledge results, and unsupported scopes are typed states rather than crashes;
- a mock module service request completes the knowledge/AI response and finalize round trip;
- commit history contains one focused commit for each task.
