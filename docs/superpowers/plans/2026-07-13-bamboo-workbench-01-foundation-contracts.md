# BambooWorkbench Foundation, Contracts, and Mock Modules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean Python project, freeze the module JSON contracts, provide a contract-validation CLI, and deliver three interchangeable mock modules.

**Architecture:** The repository exposes Pydantic models as the single source of truth for manifests, jobs, progress events, results, confirmations, and shared-service requests. JSON Schema and examples are generated from those models. Mock modules run as independent command-line processes and prove that moisture, boiling, and after-sales modules share one contract.

**Tech Stack:** Python 3.12, Pydantic 2, PyYAML, openpyxl, pytest, pytest-cov, ruff, Windows batch launchers.

## Global Constraints

- Project root is exactly `D:\Project\BambooWorkbench`.
- Product English name, folder name, and GitHub repository name are exactly `BambooWorkbench`.
- Customer-facing Chinese product name is exactly `竹简工作台`.
- First release targets Windows 10/11 and Python 3.12.
- Framework code must not implement moisture, boiling, or after-sales business rules.
- Modules must not create UI, read API keys, modify source files, or write the framework database.
- Real enterprise files, secrets, local databases, logs, and generated outputs must never be committed.
- Use TDD, focused files, UTF-8 JSON, and one independently testable commit per task.

---

## File Map

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Python, dependencies, pytest, coverage, and ruff configuration |
| `app/__init__.py` | Product identity and version |
| `core/contracts/*.py` | Canonical Pydantic contract models |
| `contracts/schemas/` | Generated JSON Schema for module developers |
| `contracts/examples/` | Valid protocol examples |
| `app/tools/export_schemas.py` | Deterministic Schema/example exporter |
| `app/tools/module_contract_cli.py` | Module package validator |
| `mock_modules/common/cli.py` | Shared independent-process mock runner |
| `mock_modules/<module_id>/` | Three mock module packages |
| `tests/unit/contracts/` | Model and schema unit tests |
| `tests/contract/` | Module package and process contract tests |

### Task 1: Create the Python project and identity contract

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `README.md`
- Create: `CHANGELOG.md`
- Create: `app/__init__.py`
- Create: `tests/unit/test_product_identity.py`

**Interfaces:**
- Produces: `app.PRODUCT_NAME_EN: str`, `app.PRODUCT_NAME_ZH: str`, `app.__version__: str`
- Consumes: none

- [ ] **Step 1: Write the failing identity test**

```python
# tests/unit/test_product_identity.py
from app import PRODUCT_NAME_EN, PRODUCT_NAME_ZH, __version__


def test_product_identity_is_canonical() -> None:
    assert PRODUCT_NAME_EN == "BambooWorkbench"
    assert PRODUCT_NAME_ZH == "竹简工作台"
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run the test and verify failure**

Run:

```powershell
python -m pytest tests/unit/test_product_identity.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Create project metadata and minimal package**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=75", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "BambooWorkbench"
version = "0.1.0"
description = "竹简工作台：可插拔的本地品质数据桌面框架"
requires-python = ">=3.12,<3.13"
dependencies = [
  "PySide6>=6.8,<7",
  "pydantic>=2.10,<3",
  "platformdirs>=4.3,<5",
  "httpx>=0.28,<1",
  "keyring>=25,<26",
  "PyYAML>=6,<7",
  "openpyxl>=3.1,<4",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3,<9",
  "pytest-cov>=6,<7",
  "pytest-qt>=4.4,<5",
  "ruff>=0.9,<1",
]
packaging = ["pyinstaller>=6.11,<7"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra --strict-markers"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
```

```text
# .python-version
3.12
```

```python
# app/__init__.py
PRODUCT_NAME_EN = "BambooWorkbench"
PRODUCT_NAME_ZH = "竹简工作台"
__version__ = "0.1.0"
```

````markdown
# BambooWorkbench（竹简工作台）

Windows本地品质数据桌面框架。第一版提供统一UI、模块协议和模拟模块，不实现三个业务模块的内部算法。

## Development

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
````

```markdown
# Changelog

## 0.1.0 - Unreleased

- Establish BambooWorkbench project identity and module contract foundation.
```

- [ ] **Step 4: Run tests and lint**

Run:

```powershell
python -m pytest tests/unit/test_product_identity.py -v
python -m ruff check app tests/unit/test_product_identity.py
```

Expected: 1 test PASS; ruff exits 0.

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml .python-version README.md CHANGELOG.md app tests/unit/test_product_identity.py
git commit -m "chore: initialize BambooWorkbench Python project"
```

### Task 2: Define shared enums and module manifest

**Files:**
- Create: `core/__init__.py`
- Create: `core/contracts/__init__.py`
- Create: `core/contracts/enums.py`
- Create: `core/contracts/manifest.py`
- Create: `tests/unit/contracts/test_manifest.py`

**Interfaces:**
- Produces: `ModuleId`, `TaskStatus`, `Severity`, `ModuleManifest`
- Consumes: Pydantic 2

- [ ] **Step 1: Write failing manifest tests**

```python
# tests/unit/contracts/test_manifest.py
import pytest
from pydantic import ValidationError

from core.contracts.enums import ModuleId, Severity, TaskStatus
from core.contracts.manifest import ModuleManifest


def test_manifest_accepts_canonical_mock_module() -> None:
    manifest = ModuleManifest.model_validate(
        {
            "schema_version": "1.0",
            "module_id": "moisture",
            "module_name": "原竹丝水分检测",
            "module_version": "0.1.0",
            "entrypoint": "run_module.bat",
            "supported_extensions": [".xlsx"],
            "supports_single_file": True,
            "supports_batch": True,
            "supports_incremental": True,
            "requires_network": False,
        }
    )
    assert manifest.module_id is ModuleId.MOISTURE
    assert Severity.WARNING.value == "warning"
    assert TaskStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"


def test_manifest_rejects_non_semantic_version() -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate(
            {
                "schema_version": "1.0",
                "module_id": "moisture",
                "module_name": "x",
                "module_version": "latest",
                "entrypoint": "run_module.bat",
                "supported_extensions": [".xlsx"],
                "supports_single_file": True,
                "supports_batch": True,
                "supports_incremental": False,
                "requires_network": False,
            }
        )
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/unit/contracts/test_manifest.py -v`
Expected: FAIL because `core.contracts` does not exist.

- [ ] **Step 3: Implement enums and manifest**

```python
# core/contracts/enums.py
from enum import StrEnum


class ModuleId(StrEnum):
    MOISTURE = "moisture"
    BOILING = "boiling"
    AFTER_SALES = "after_sales"


class TaskStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    NEEDS_CONFIRMATION = "needs_confirmation"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
```

```python
# core/contracts/manifest.py
from pydantic import BaseModel, ConfigDict, Field

from .enums import ModuleId


class ModuleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    module_id: ModuleId
    module_name: str = Field(min_length=1, max_length=80)
    module_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    entrypoint: str = Field(min_length=1)
    supported_extensions: list[str] = Field(min_length=1)
    supports_single_file: bool
    supports_batch: bool
    supports_incremental: bool
    requires_network: bool
```

```python
# core/contracts/__init__.py
from .enums import ModuleId, Severity, TaskStatus
from .manifest import ModuleManifest

__all__ = ["ModuleId", "ModuleManifest", "Severity", "TaskStatus"]
```

`core/__init__.py` is an empty UTF-8 file.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/contracts/test_manifest.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add core tests/unit/contracts/test_manifest.py
git commit -m "feat: define module manifest contract"
```

### Task 3: Define draft and finalize job contracts

**Files:**
- Create: `core/contracts/job.py`
- Modify: `core/contracts/enums.py`
- Modify: `core/contracts/__init__.py`
- Create: `tests/unit/contracts/test_job.py`

**Interfaces:**
- Produces: `JobPhase`, `RunMode`, `JobRequest`
- Consumes: `ModuleId`

- [ ] **Step 1: Write failing job tests**

```python
# tests/unit/contracts/test_job.py
import pytest
from pydantic import ValidationError

from core.contracts.job import JobRequest


def test_draft_job_requires_absolute_inputs() -> None:
    job = JobRequest.model_validate(
        {
            "schema_version": "1.0",
            "job_id": "20260713-0001",
            "module_id": "moisture",
            "phase": "draft",
            "run_mode": "batch",
            "input_files": ["D:/data/example.xlsx"],
            "output_dir": "D:/output/20260713-0001",
            "module_config_file": None,
            "ai_enabled": False,
            "allowed_knowledge_scopes": ["shared", "moisture"],
        }
    )
    assert job.phase.value == "draft"
    assert job.confirmation_file is None


def test_finalize_job_requires_confirmation_file() -> None:
    with pytest.raises(ValidationError):
        JobRequest.model_validate(
            {
                "schema_version": "1.0",
                "job_id": "20260713-0002",
                "module_id": "moisture",
                "phase": "finalize",
                "run_mode": "batch",
                "input_files": ["D:/data/example.xlsx"],
                "output_dir": "D:/output/20260713-0002",
                "parent_job_id": "20260713-0001",
                "ai_enabled": False,
                "allowed_knowledge_scopes": ["shared", "moisture"],
            }
        )
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/contracts/test_job.py -v`
Expected: FAIL because `core.contracts.job` is missing.

- [ ] **Step 3: Implement job model**

```python
# additions to core/contracts/enums.py
class JobPhase(StrEnum):
    DRAFT = "draft"
    FINALIZE = "finalize"


class RunMode(StrEnum):
    SINGLE = "single"
    BATCH = "batch"
    INCREMENTAL = "incremental"
```

```python
# core/contracts/job.py
from pathlib import PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import JobPhase, ModuleId, RunMode


def _is_absolute(path: str) -> bool:
    return PureWindowsPath(path).is_absolute()


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    phase: JobPhase
    run_mode: RunMode
    input_files: list[str] = Field(min_length=1)
    output_dir: str
    module_config_file: str | None = None
    ai_enabled: bool = False
    allowed_knowledge_scopes: list[str] = Field(default_factory=list)
    parent_job_id: str | None = None
    confirmation_file: str | None = None
    service_response_file: str | None = None

    @model_validator(mode="after")
    def validate_paths_and_phase(self) -> "JobRequest":
        paths = [*self.input_files, self.output_dir]
        optional_paths = [self.module_config_file, self.confirmation_file, self.service_response_file]
        paths.extend(path for path in optional_paths if path is not None)
        if not all(_is_absolute(path) for path in paths):
            raise ValueError("all job paths must be absolute Windows paths")
        if self.phase is JobPhase.FINALIZE:
            if not self.parent_job_id or not self.confirmation_file:
                raise ValueError("finalize jobs require parent_job_id and confirmation_file")
        return self
```

Update `core/contracts/__init__.py` to export `JobPhase`, `RunMode`, and `JobRequest`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/contracts/test_job.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add core/contracts tests/unit/contracts/test_job.py
git commit -m "feat: define module job contract"
```

### Task 4: Define progress, result, confirmation, and service contracts

**Files:**
- Create: `core/contracts/progress.py`
- Create: `core/contracts/result.py`
- Create: `core/contracts/confirmation.py`
- Create: `core/contracts/service_request.py`
- Modify: `core/contracts/__init__.py`
- Create: `tests/unit/contracts/test_result.py`

**Interfaces:**
- Produces: `ProgressEvent`, `Anomaly`, `ConfirmationPrompt`, `OutputArtifact`, `FileResult`, `ServiceRequest`, `ModuleResult`, `ConfirmationAnswer`, `ConfirmationBundle`
- Consumes: `ModuleId`, `Severity`, `TaskStatus`

- [ ] **Step 1: Write failing result tests**

```python
# tests/unit/contracts/test_result.py
import pytest
from pydantic import ValidationError

from core.contracts.progress import ProgressEvent
from core.contracts.result import ModuleResult


def test_progress_percent_is_bounded() -> None:
    assert ProgressEvent(type="progress", percent=40, message="处理中").percent == 40
    with pytest.raises(ValidationError):
        ProgressEvent(type="progress", percent=101, message="invalid")


def test_confirmation_result_requires_prompts() -> None:
    with pytest.raises(ValidationError):
        ModuleResult.model_validate(
            {
                "schema_version": "1.0",
                "job_id": "20260713-0001",
                "module_id": "moisture",
                "module_version": "0.1.0",
                "status": "needs_confirmation",
                "summary": {
                    "input_count": 1,
                    "processed_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "anomaly_count": 0,
                    "confirmation_count": 0,
                },
                "confirmations": [],
                "started_at": "2026-07-13T09:00:00+08:00",
                "finished_at": "2026-07-13T09:00:01+08:00",
            }
        )
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/contracts/test_result.py -v`
Expected: FAIL because result models are missing.

- [ ] **Step 3: Implement the contracts**

```python
# core/contracts/progress.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["progress"]
    percent: int = Field(ge=0, le=100)
    message: str = Field(min_length=1, max_length=300)
    source_file: str | None = None
```

```python
# core/contracts/service_request.py
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    service: Literal["knowledge", "ai"]
    scope: str | None = None
    purpose: str = Field(min_length=1, max_length=300)
    payload: dict[str, object]
    requires_user_consent: bool = True
```

```python
# core/contracts/confirmation.py
from pydantic import BaseModel, ConfigDict


class ConfirmationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: str
    value: object
    apply_to_batch: bool = False
    remember_mapping: bool = False


class ConfirmationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    job_id: str
    answers: list[ConfirmationAnswer]
```

```python
# core/contracts/result.py
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ModuleId, Severity, TaskStatus
from .service_request import ServiceRequest


class ResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_count: int = Field(ge=0)
    processed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)
    confirmation_count: int = Field(ge=0)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_file: str
    sheet: str | None = None
    cell_or_range: str | None = None


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anomaly_id: str
    severity: Severity
    field: str
    value: object | None = None
    rule_id: str | None = None
    message: str
    suggestion: str | None = None
    source: SourceRef


class ConfirmationPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_id: str
    field: str
    reason: str
    suggested_value: object | None = None
    options: list[object] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    blocking: bool
    batch_applicable: bool
    rememberable: bool
    source: SourceRef


class OutputArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    path: str
    label: str
    mime_type: str


class FileResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_file: str
    fingerprint: str
    status: TaskStatus
    extracted_records: int = Field(ge=0)
    missing_fields: list[str] = Field(default_factory=list)
    anomaly_count: int = Field(ge=0)
    error: str | None = None


class ModuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = Field(pattern=r"^1\.0$")
    job_id: str
    module_id: ModuleId
    module_version: str
    status: TaskStatus
    rule_version: str | None = None
    summary: ResultSummary
    anomalies: list[Anomaly] = Field(default_factory=list)
    confirmations: list[ConfirmationPrompt] = Field(default_factory=list)
    outputs: list[OutputArtifact] = Field(default_factory=list)
    file_results: list[FileResult] = Field(default_factory=list)
    service_requests: list[ServiceRequest] = Field(default_factory=list)
    analysis_summary: str | None = None
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_confirmation_state(self) -> "ModuleResult":
        if self.status is TaskStatus.NEEDS_CONFIRMATION and not self.confirmations:
            raise ValueError("needs_confirmation requires at least one prompt")
        if self.summary.confirmation_count != len(self.confirmations):
            raise ValueError("confirmation_count must equal confirmation list length")
        return self
```

Export all new models from `core/contracts/__init__.py`.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/contracts/test_result.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add core/contracts tests/unit/contracts/test_result.py
git commit -m "feat: define result and confirmation contracts"
```

### Task 5: Export deterministic Schema and examples

**Files:**
- Create: `app/tools/__init__.py`
- Create: `app/tools/export_schemas.py`
- Create: `tests/unit/contracts/test_schema_export.py`
- Generate: `contracts/schemas/*.schema.json`
- Generate: `contracts/examples/*.json`

**Interfaces:**
- Produces: `export_contracts(root: Path) -> list[Path]`
- Consumes: all contract models from Tasks 2-4

- [ ] **Step 1: Write failing export test**

```python
# tests/unit/contracts/test_schema_export.py
import json
from pathlib import Path

from app.tools.export_schemas import export_contracts


def test_export_contracts_writes_valid_json(tmp_path: Path) -> None:
    written = export_contracts(tmp_path)
    names = {path.name for path in written}
    assert "module-manifest.schema.json" in names
    assert "job-request.schema.json" in names
    assert "module-result.schema.json" in names
    for path in written:
        json.loads(path.read_text(encoding="utf-8"))
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/contracts/test_schema_export.py -v`
Expected: FAIL because `export_schemas` is missing.

- [ ] **Step 3: Implement exporter**

```python
# app/tools/export_schemas.py
import json
from pathlib import Path

from core.contracts.job import JobRequest
from core.contracts.manifest import ModuleManifest
from core.contracts.result import ModuleResult


MODELS = {
    "module-manifest.schema.json": ModuleManifest,
    "job-request.schema.json": JobRequest,
    "module-result.schema.json": ModuleResult,
}


def export_contracts(root: Path) -> list[Path]:
    schema_dir = root / "contracts" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, model in MODELS.items():
        path = schema_dir / filename
        text = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
        path.write_text(text + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    export_contracts(Path.cwd())
```

- [ ] **Step 4: Run exporter and tests**

Run:

```powershell
python -m app.tools.export_schemas
python -m pytest tests/unit/contracts/test_schema_export.py -v
```

Expected: 1 test PASS and three Schema files exist.

- [ ] **Step 5: Commit**

```powershell
git add app/tools core/contracts contracts tests/unit/contracts/test_schema_export.py
git commit -m "feat: export module contract schemas"
```

### Task 6: Build the module package validator

**Files:**
- Create: `core/contracts/validator.py`
- Create: `app/tools/module_contract_cli.py`
- Create: `tests/contract/test_static_validator.py`

**Interfaces:**
- Produces: `ValidationIssue`, `ValidationReport`, `validate_module(module_dir: Path) -> ValidationReport`
- Consumes: `ModuleManifest`

- [ ] **Step 1: Write failing validator tests**

```python
# tests/contract/test_static_validator.py
import json
from pathlib import Path

from core.contracts.validator import validate_module


def test_validator_reports_missing_required_files(tmp_path: Path) -> None:
    report = validate_module(tmp_path)
    assert report.ok is False
    assert {issue.code for issue in report.issues} >= {"missing-module-json", "missing-entrypoint"}


def test_validator_accepts_minimal_module(tmp_path: Path) -> None:
    manifest = {
        "schema_version": "1.0",
        "module_id": "moisture",
        "module_name": "原竹丝水分检测",
        "module_version": "0.1.0",
        "entrypoint": "run_module.bat",
        "supported_extensions": [".xlsx"],
        "supports_single_file": True,
        "supports_batch": True,
        "supports_incremental": True,
        "requires_network": False,
    }
    (tmp_path / "module.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "run_module.bat").write_text("@echo off\nexit /b 0\n", encoding="utf-8")
    for name in ["README.md", "CHANGELOG.md", "requirements.txt"]:
        (tmp_path / name).write_text("ok\n", encoding="utf-8")
    for name in ["src", "tests", "samples", "docs"]:
        (tmp_path / name).mkdir()
    assert validate_module(tmp_path).ok is True
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/contract/test_static_validator.py -v`
Expected: FAIL because validator is missing.

- [ ] **Step 3: Implement static validator and CLI**

```python
# core/contracts/validator.py
import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .manifest import ModuleManifest


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def validate_module(module_dir: Path) -> ValidationReport:
    report = ValidationReport()
    manifest_path = module_dir / "module.json"
    if not manifest_path.is_file():
        report.issues.append(ValidationIssue("missing-module-json", "module.json is required"))
        report.issues.append(ValidationIssue("missing-entrypoint", "entrypoint cannot be resolved"))
        return report
    try:
        manifest = ModuleManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValidationError) as exc:
        report.issues.append(ValidationIssue("invalid-module-json", str(exc)))
        return report
    required_files = ["README.md", "CHANGELOG.md", "requirements.txt", manifest.entrypoint]
    required_dirs = ["src", "tests", "samples", "docs"]
    for name in required_files:
        if not (module_dir / name).is_file():
            code = "missing-entrypoint" if name == manifest.entrypoint else "missing-required-file"
            report.issues.append(ValidationIssue(code, f"missing file: {name}"))
    for name in required_dirs:
        if not (module_dir / name).is_dir():
            report.issues.append(ValidationIssue("missing-required-directory", f"missing directory: {name}"))
    return report
```

```python
# app/tools/module_contract_cli.py
import argparse
from pathlib import Path

from core.contracts.validator import validate_module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate"])
    parser.add_argument("module_dir", type=Path)
    args = parser.parse_args()
    report = validate_module(args.module_dir.resolve())
    for issue in report.issues:
        print(f"{issue.code}: {issue.message}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests and CLI**

Run:

```powershell
python -m pytest tests/contract/test_static_validator.py -v
python -m app.tools.module_contract_cli validate mock_modules\moisture
```

Expected before Task 8: tests PASS; CLI returns 1 because the mock module does not exist yet.

- [ ] **Step 5: Commit**

```powershell
git add core/contracts/validator.py app/tools/module_contract_cli.py tests/contract/test_static_validator.py
git commit -m "feat: add module package validator"
```

### Task 7: Implement the shared mock-module process

**Files:**
- Create: `mock_modules/__init__.py`
- Create: `mock_modules/common/__init__.py`
- Create: `mock_modules/common/cli.py`
- Create: `mock_modules/common/scenarios.py`
- Create: `mock_modules/common/artifacts.py`
- Create: `tests/contract/test_mock_runner.py`

**Interfaces:**
- Produces: command `python -m mock_modules.common.cli --module-id <id> <version|self-check|run>`
- Consumes: `JobRequest`, `ModuleResult`, `ConfirmationBundle`

- [ ] **Step 1: Write the failing runner test**

```python
# tests/contract/test_mock_runner.py
import json
import subprocess
import sys
from pathlib import Path


def test_mock_runner_creates_success_result(tmp_path: Path) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job = {
        "schema_version": "1.0",
        "job_id": "mock-0001",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": ["shared", "moisture"],
    }
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "mock_modules.common.cli", "--module-id", "moisture", "run", "--job", str(job_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/contract/test_mock_runner.py -v`
Expected: FAIL because mock runner is missing.

- [ ] **Step 3: Implement minimal mock runner**

```python
# mock_modules/common/artifacts.py
from pathlib import Path

from openpyxl import Workbook


def create_artifacts(output_dir: Path, module_id: str) -> list[dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = output_dir / f"{module_id}-summary.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Summary"
    sheet.append(["Module", "Status"])
    sheet.append([module_id, "Mock success"])
    workbook.save(workbook_path)
    report_path = output_dir / f"{module_id}-report.md"
    report_path.write_text(f"# {module_id}\n\nMock analysis result.\n", encoding="utf-8")
    chart_path = output_dir / f"{module_id}-chart.svg"
    chart_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="240">'
        '<rect width="600" height="240" fill="#fbfaf4"/>'
        '<rect x="50" y="80" width="120" height="110" fill="#2fa47d"/>'
        '<rect x="210" y="40" width="120" height="150" fill="#294d3c"/>'
        '<rect x="370" y="110" width="120" height="80" fill="#f1b232"/>'
        "</svg>",
        encoding="utf-8",
    )
    return [
        {"type": "summary_excel", "path": str(workbook_path.resolve()), "label": "模拟汇总", "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
        {"type": "report", "path": str(report_path.resolve()), "label": "模拟报告", "mime_type": "text/markdown"},
        {"type": "chart", "path": str(chart_path.resolve()), "label": "模拟图表", "mime_type": "image/svg+xml"},
    ]
```

```python
# mock_modules/common/scenarios.py
from pathlib import Path


def scenario_for(inputs: list[str]) -> str:
    names = " ".join(Path(path).name.lower() for path in inputs)
    for scenario in ["confirm", "partial", "fail", "invalid", "timeout", "crash", "ai", "knowledge"]:
        if scenario in names:
            return scenario
    return "success"
```

```python
# mock_modules/common/cli.py
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult

from .artifacts import create_artifacts
from .scenarios import scenario_for


def now() -> str:
    return datetime.now().astimezone().isoformat()


def run(module_id: str, job_path: Path) -> int:
    job = JobRequest.model_validate_json(job_path.read_text(encoding="utf-8"))
    output_dir = Path(job.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario = scenario_for(job.input_files)
    if scenario == "crash":
        return 3
    if scenario == "timeout":
        time.sleep(120)
    started = now()
    print(json.dumps({"type": "progress", "percent": 25, "message": "读取模拟输入"}, ensure_ascii=False), flush=True)
    artifacts = create_artifacts(output_dir, module_id)
    print(json.dumps({"type": "progress", "percent": 100, "message": "模拟处理完成"}, ensure_ascii=False), flush=True)
    confirmations = []
    status = "success"
    if scenario == "confirm" and job.phase.value == "draft":
        status = "needs_confirmation"
        confirmations = [{
            "confirmation_id": "mock-confirm-1",
            "field": "mock_field",
            "reason": "模拟边界问题",
            "suggested_value": "建议值",
            "options": ["建议值", "人工值"],
            "confidence": 0.5,
            "blocking": True,
            "batch_applicable": True,
            "rememberable": False,
            "source": {"source_file": job.input_files[0], "sheet": None, "cell_or_range": None},
        }]
    result = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "module_id": module_id,
        "module_version": "0.1.0",
        "status": status,
        "rule_version": "mock-1.0",
        "summary": {
            "input_count": len(job.input_files),
            "processed_count": len(job.input_files),
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 0,
            "confirmation_count": len(confirmations),
        },
        "anomalies": [],
        "confirmations": confirmations,
        "outputs": artifacts,
        "file_results": [{
            "source_file": path,
            "fingerprint": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "status": "success",
            "extracted_records": 1,
            "missing_fields": [],
            "anomaly_count": 0,
            "error": None,
        } for path in job.input_files],
        "service_requests": [],
        "analysis_summary": "模拟模块运行成功",
        "errors": [],
        "started_at": started,
        "finished_at": now(),
    }
    validated = ModuleResult.model_validate(result)
    (output_dir / "result.json").write_text(validated.model_dump_json(indent=2), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module-id", required=True, choices=["moisture", "boiling", "after_sales"])
    parser.add_argument("command", choices=["version", "self-check", "run"])
    parser.add_argument("--job", type=Path)
    args = parser.parse_args()
    if args.command == "version":
        print("0.1.0")
        return 0
    if args.command == "self-check":
        print("ok")
        return 0
    if args.job is None:
        parser.error("run requires --job")
    return run(args.module_id, args.job.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test**

Run: `python -m pytest tests/contract/test_mock_runner.py -v`
Expected: 1 test PASS and stdout contains two valid progress lines.

- [ ] **Step 5: Commit**

```powershell
git add mock_modules tests/contract/test_mock_runner.py
git commit -m "feat: add shared mock module runner"
```

### Task 8: Package all three mock modules and validate them

**Files:**
- Create: `mock_modules/moisture/module.json`
- Create: `mock_modules/moisture/run_module.bat`
- Create: equivalent files for `boiling` and `after_sales`
- Create: required README, CHANGELOG, requirements, src, tests, samples, and docs directories for each
- Create: `tests/contract/test_all_mock_modules.py`

**Interfaces:**
- Produces: three module directories accepted by `validate_module()`
- Consumes: shared mock CLI from Task 7

- [ ] **Step 1: Write failing parameterized test**

```python
# tests/contract/test_all_mock_modules.py
from pathlib import Path

import pytest

from core.contracts.validator import validate_module


@pytest.mark.parametrize("module_id", ["moisture", "boiling", "after_sales"])
def test_mock_module_package_is_valid(module_id: str) -> None:
    module_dir = Path("mock_modules") / module_id
    report = validate_module(module_dir)
    assert report.ok, [issue.message for issue in report.issues]
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/contract/test_all_mock_modules.py -v`
Expected: 3 failures because package files are missing.

- [ ] **Step 3: Create the three packages**

Use this exact `module.json` for moisture and change only `module_id` and `module_name` for the other two:

```json
{
  "schema_version": "1.0",
  "module_id": "moisture",
  "module_name": "原竹丝水分检测",
  "module_version": "0.1.0",
  "entrypoint": "run_module.bat",
  "supported_extensions": [".xlsx"],
  "supports_single_file": true,
  "supports_batch": true,
  "supports_incremental": true,
  "requires_network": false
}
```

Use this launcher and replace the module id in each package:

```bat
@echo off
setlocal
python -m mock_modules.common.cli --module-id moisture %*
exit /b %ERRORLEVEL%
```

Each README states that the package is a non-business mock. Each `requirements.txt` contains `-e .`. Each required directory contains a `.gitkeep`, and `samples/input/normal.xlsx` may be an empty marker file because the mock does not parse it.

- [ ] **Step 4: Run package and process checks**

Run:

```powershell
python -m pytest tests/contract/test_all_mock_modules.py -v
python -m app.tools.module_contract_cli validate mock_modules\moisture
python -m app.tools.module_contract_cli validate mock_modules\boiling
python -m app.tools.module_contract_cli validate mock_modules\after_sales
```

Expected: 3 tests PASS and all CLI commands return 0.

- [ ] **Step 5: Commit**

```powershell
git add mock_modules tests/contract/test_all_mock_modules.py
git commit -m "feat: package three contract-compliant mock modules"
```

### Task 9: Add finalize and malformed-output contract coverage

**Files:**
- Modify: `mock_modules/common/cli.py`
- Modify: `mock_modules/common/scenarios.py`
- Create: `tests/contract/test_mock_scenarios.py`

**Interfaces:**
- Produces: deterministic mock behaviors for `confirm`, `partial`, `fail`, `invalid`, `timeout`, `crash`, `ai`, and `knowledge`
- Consumes: `JobRequest`, `ConfirmationBundle`, `ServiceRequest`

- [ ] **Step 1: Write failing scenario tests**

```python
# tests/contract/test_mock_scenarios.py
import json
import subprocess
import sys
from pathlib import Path

import pytest


def run_mock(tmp_path: Path, scenario: str, phase: str = "draft") -> tuple[int, dict[str, object] | None]:
    input_file = tmp_path / f"{scenario}.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / f"out-{scenario}-{phase}"
    confirmation_file = None
    if phase == "finalize":
        confirmation_path = tmp_path / "confirmation.json"
        confirmation_path.write_text(
            json.dumps({"schema_version": "1.0", "job_id": "parent-1", "answers": [{"confirmation_id": "mock-confirm-1", "value": "人工值", "apply_to_batch": False, "remember_mapping": False}]}),
            encoding="utf-8",
        )
        confirmation_file = str(confirmation_path.resolve())
    job = {
        "schema_version": "1.0",
        "job_id": f"job-{scenario}-{phase}",
        "module_id": "moisture",
        "phase": phase,
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
        "module_config_file": None,
        "ai_enabled": scenario == "ai",
        "allowed_knowledge_scopes": ["shared", "moisture"],
        "parent_job_id": "parent-1" if phase == "finalize" else None,
        "confirmation_file": confirmation_file,
        "service_response_file": None,
    }
    job_path = tmp_path / f"job-{scenario}-{phase}.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-m", "mock_modules.common.cli", "--module-id", "moisture", "run", "--job", str(job_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    result_path = output_dir / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else None
    return completed.returncode, result


def test_confirmation_finalizes_after_answer(tmp_path: Path) -> None:
    assert run_mock(tmp_path, "confirm")[1]["status"] == "needs_confirmation"
    assert run_mock(tmp_path, "confirm", "finalize")[1]["status"] == "success"


@pytest.mark.parametrize("scenario,expected", [("partial", "partial_success"), ("fail", "failed")])
def test_status_scenarios(tmp_path: Path, scenario: str, expected: str) -> None:
    assert run_mock(tmp_path, scenario)[1]["status"] == expected


def test_crash_has_no_result(tmp_path: Path) -> None:
    code, result = run_mock(tmp_path, "crash")
    assert code == 3
    assert result is None
```

- [ ] **Step 2: Run and verify failures**

Run: `python -m pytest tests/contract/test_mock_scenarios.py -v`
Expected: confirmation may pass, but partial/fail scenarios FAIL because Task 7 always emits success.

- [ ] **Step 3: Implement explicit scenarios**

In `mock_modules/common/cli.py`, immediately after determining `scenario`, set `status`, counts, service requests, and output behavior using this complete mapping:

```python
status = "success"
failed_count = 0
errors: list[str] = []
service_requests: list[dict[str, object]] = []
if scenario == "partial":
    status = "partial_success"
    failed_count = 1
    errors = ["模拟单文件失败"]
elif scenario == "fail":
    status = "failed"
    failed_count = len(job.input_files)
    errors = ["模拟任务失败"]
elif scenario == "invalid":
    (output_dir / "result.json").write_text("{invalid", encoding="utf-8")
    return 0
elif scenario == "ai":
    service_requests = [{"request_id": "ai-1", "service": "ai", "scope": None, "purpose": "生成模拟分析", "payload": {"metrics": [1, 2, 3]}, "requires_user_consent": True}]
elif scenario == "knowledge":
    service_requests = [{"request_id": "kb-1", "service": "knowledge", "scope": module_id, "purpose": "检索模拟规则", "payload": {"query": "异常处理"}, "requires_user_consent": False}]
if scenario == "confirm" and job.phase.value == "finalize":
    status = "success"
    confirmations = []
```

Use `failed_count`, `errors`, and `service_requests` in the result; set `processed_count` to `len(inputs) - failed_count`. For failed tasks, leave outputs empty. For partial tasks, keep outputs and mark the first `FileResult` failed.

- [ ] **Step 4: Run the complete Plan 1 suite**

Run:

```powershell
python -m pytest tests/unit/contracts tests/contract -v
python -m ruff check app core mock_modules tests
```

Expected: all tests PASS and ruff exits 0.

- [ ] **Step 5: Commit**

```powershell
git add mock_modules/common tests/contract/test_mock_scenarios.py
git commit -m "test: cover mock module lifecycle scenarios"
```

## Plan 1 Completion Gate

Run:

```powershell
python -m pytest tests/unit/contracts tests/contract --cov=core.contracts --cov=mock_modules -v
python -m app.tools.module_contract_cli validate mock_modules\moisture
python -m app.tools.module_contract_cli validate mock_modules\boiling
python -m app.tools.module_contract_cli validate mock_modules\after_sales
```

Expected:

- all tests PASS;
- all three validators return 0;
- draft and finalize scenarios produce valid result files;
- malformed and crashed modules are reproducible for Plan 2;
- no PySide6 window is required yet.
