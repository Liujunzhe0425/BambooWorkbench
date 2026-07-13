# BambooWorkbench Desktop Runtime and Unified UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a fully operable PySide6 desktop framework that runs all three mock modules through independent processes, persists task history, completes two-stage confirmation, and displays unified results.

**Architecture:** Application services own task orchestration, module execution, persistence, and confirmation; PySide6 pages call those services and never invoke module processes directly. QProcess isolates modules and parses stdout JSONL into typed progress events. SQLite and task-local directories preserve framework history without storing module business tables.

**Tech Stack:** Python 3.12, PySide6/QProcess, Pydantic 2 contracts from Plan 1, sqlite3, platformdirs, pytest, pytest-qt.

## Global Constraints

- Complete Plan 1 before starting this plan.
- Project root is `D:\Project\BambooWorkbench`.
- Product name is `BambooWorkbench`; customer-facing name is `竹简工作台`.
- First release is a local, single-user Windows 10/11 desktop application with no login.
- Framework owns all UI; modules must remain UI-free independent processes.
- Source inputs are never modified; task snapshots and outputs remain local.
- Use the approved ivory, bamboo green, navy, and warm-gold visual baseline.
- Do not implement moisture, boiling, or after-sales business rules.
- Use TDD and commit after every independently testable task.

---

## File Map

| Path | Responsibility |
|---|---|
| `core/platform/paths.py` | Canonical local directories |
| `core/storage/database.py` | SQLite lifecycle and migrations |
| `core/storage/repositories/*.py` | Task/module/confirmation persistence |
| `core/modules/registry.py` | Module discovery and health state |
| `core/modules/process_runner.py` | QProcess lifecycle and JSONL progress |
| `core/tasks/*.py` | Task state machine, snapshots, and orchestration |
| `core/confirmations/service.py` | Confirmation persistence and finalize jobs |
| `ui/main_window.py` | Application shell and navigation |
| `ui/pages/*.py` | Workbench, task, progress, confirmation, result, history, knowledge, settings |
| `ui/widgets/*.py` | Reusable visual components |
| `tests/integration/` | Process and task-flow tests |
| `tests/ui/` | pytest-qt page and journey tests |

### Task 1: Establish local paths, SQLite, and settings

**Files:**
- Create: `core/platform/__init__.py`
- Create: `core/platform/paths.py`
- Create: `core/storage/__init__.py`
- Create: `core/storage/database.py`
- Create: `core/storage/settings.py`
- Create: `tests/unit/storage/test_paths_database.py`

**Interfaces:**
- Produces: `AppPaths.for_root(root: Path | None) -> AppPaths`, `Database.open(paths: AppPaths) -> Database`, `SettingsStore`
- Consumes: `platformdirs.user_data_path`

- [ ] **Step 1: Write failing storage tests**

```python
# tests/unit/storage/test_paths_database.py
from pathlib import Path

from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.settings import SettingsStore


def test_paths_create_required_directories(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path / "BambooWorkbench")
    paths.ensure()
    assert paths.database.parent.is_dir()
    assert paths.tasks.is_dir()
    assert paths.logs.is_dir()


def test_database_migrates_once_and_settings_round_trip(tmp_path: Path) -> None:
    paths = AppPaths.for_root(tmp_path)
    paths.ensure()
    database = Database.open(paths)
    database.migrate()
    database.migrate()
    settings = SettingsStore(database)
    settings.set("output_dir", "D:/exports")
    assert settings.get("output_dir") == "D:/exports"
    assert database.scalar("SELECT version FROM schema_version") == 1
```

- [ ] **Step 2: Run tests and verify failure**

Run: `python -m pytest tests/unit/storage/test_paths_database.py -v`
Expected: FAIL because path and database classes do not exist.

- [ ] **Step 3: Implement paths, database, and settings**

```python
# core/platform/paths.py
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    modules: Path
    knowledge: Path
    tasks: Path
    logs: Path
    cache: Path

    @classmethod
    def for_root(cls, root: Path | None = None) -> "AppPaths":
        resolved = (root or user_data_path("BambooWorkbench", appauthor=False)).resolve()
        return cls(
            root=resolved,
            database=resolved / "data" / "app.db",
            modules=resolved / "modules",
            knowledge=resolved / "knowledge",
            tasks=resolved / "tasks",
            logs=resolved / "logs",
            cache=resolved / "cache",
        )

    def ensure(self) -> None:
        for path in [self.database.parent, self.modules, self.knowledge, self.tasks, self.logs, self.cache]:
            path.mkdir(parents=True, exist_ok=True)
```

```python
# core/storage/database.py
import sqlite3
from pathlib import Path
from typing import Any

from core.platform.paths import AppPaths


MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version(version)
SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM schema_version);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    @classmethod
    def open(cls, paths: AppPaths) -> "Database":
        paths.ensure()
        return cls(paths.database)

    def migrate(self) -> None:
        self.connection.executescript(MIGRATION_1)
        current = self.scalar("SELECT version FROM schema_version")
        if current == 0:
            self.connection.execute("UPDATE schema_version SET version = 1")
            self.connection.commit()

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        cursor = self.connection.execute(sql, parameters)
        self.connection.commit()
        return cursor

    def scalar(self, sql: str, parameters: tuple[Any, ...] = ()) -> Any:
        row = self.connection.execute(sql, parameters).fetchone()
        return None if row is None else row[0]
```

```python
# core/storage/settings.py
from core.storage.database import Database


class SettingsStore:
    def __init__(self, database: Database) -> None:
        self.database = database

    def set(self, key: str, value: str) -> None:
        self.database.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self.database.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return default if value is None else str(value)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/storage/test_paths_database.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add core/platform core/storage tests/unit/storage/test_paths_database.py
git commit -m "feat: add local paths and sqlite foundation"
```

### Task 2: Persist tasks, files, modules, confirmations, and outputs

**Files:**
- Modify: `core/storage/database.py`
- Create: `core/storage/repositories/tasks.py`
- Create: `core/storage/repositories/modules.py`
- Create: `core/storage/repositories/confirmations.py`
- Create: `tests/unit/storage/test_repositories.py`

**Interfaces:**
- Produces: `TaskRepository`, `ModuleRepository`, `ConfirmationRepository`
- Consumes: `Database`, contract enum string values

- [ ] **Step 1: Write failing repository test**

```python
# tests/unit/storage/test_repositories.py
from pathlib import Path

from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.tasks import TaskRepository


def test_task_repository_records_lifecycle(tmp_path: Path) -> None:
    database = Database.open(AppPaths.for_root(tmp_path))
    database.migrate()
    repository = TaskRepository(database)
    repository.create("job-001", "moisture", "created", "2026-07-13T10:00:00+08:00")
    repository.update_status("job-001", "running_draft")
    record = repository.get("job-001")
    assert record["module_id"] == "moisture"
    assert record["status"] == "running_draft"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/storage/test_repositories.py -v`
Expected: FAIL because repository and tables are missing.

- [ ] **Step 3: Add migration tables and repositories**

Append to migration 1 before setting the version:

```sql
CREATE TABLE IF NOT EXISTS tasks (
    job_id TEXT PRIMARY KEY,
    module_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    parent_job_id TEXT,
    result_path TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS task_files (
    job_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    snapshot_path TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    PRIMARY KEY(job_id, source_path)
);
CREATE TABLE IF NOT EXISTS modules (
    module_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    path TEXT NOT NULL,
    is_mock INTEGER NOT NULL,
    health TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS confirmations (
    job_id TEXT NOT NULL,
    confirmation_id TEXT NOT NULL,
    original_prompt TEXT NOT NULL,
    answer TEXT,
    answered_at TEXT,
    PRIMARY KEY(job_id, confirmation_id)
);
CREATE TABLE IF NOT EXISTS outputs (
    job_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    label TEXT NOT NULL
);
```

```python
# core/storage/repositories/tasks.py
from datetime import datetime

from core.storage.database import Database


class TaskRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, job_id: str, module_id: str, status: str, created_at: str, parent_job_id: str | None = None) -> None:
        self.database.execute(
            "INSERT INTO tasks(job_id,module_id,status,created_at,updated_at,parent_job_id) VALUES(?,?,?,?,?,?)",
            (job_id, module_id, status, created_at, created_at, parent_job_id),
        )

    def update_status(self, job_id: str, status: str, error: str | None = None, result_path: str | None = None) -> None:
        updated_at = datetime.now().astimezone().isoformat()
        self.database.execute(
            "UPDATE tasks SET status=?,updated_at=?,error=COALESCE(?,error),result_path=COALESCE(?,result_path) WHERE job_id=?",
            (status, updated_at, error, result_path, job_id),
        )

    def get(self, job_id: str) -> dict[str, object]:
        row = self.database.connection.execute("SELECT * FROM tasks WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return dict(row)

    def list_recent(self, limit: int = 20) -> list[dict[str, object]]:
        rows = self.database.connection.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
```

Implement `ModuleRepository` with `upsert()` and `list_all()`. Implement `ConfirmationRepository.save_prompts(job_id, prompts)`, `save_answers(job_id, answers)`, and `list_for_job(job_id)`; `save_answers` updates `answer` and `answered_at` by `(job_id, confirmation_id)` and raises `KeyError` when an answer does not match a stored prompt.

- [ ] **Step 4: Run repository tests**

Run: `python -m pytest tests/unit/storage/test_repositories.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add core/storage tests/unit/storage/test_repositories.py
git commit -m "feat: persist framework task lifecycle"
```

### Task 3: Discover and health-check mock or real modules

**Files:**
- Create: `core/modules/__init__.py`
- Create: `core/modules/registry.py`
- Create: `core/modules/healthcheck.py`
- Create: `tests/unit/modules/test_registry.py`

**Interfaces:**
- Produces: `RegisteredModule`, `ModuleRegistry.scan()`, `ModuleRegistry.get(ModuleId)`
- Consumes: `ModuleManifest`, static validator, `ModuleRepository`

- [ ] **Step 1: Write failing registry test**

```python
# tests/unit/modules/test_registry.py
from pathlib import Path

from core.contracts.enums import ModuleId
from core.modules.registry import ModuleRegistry


def test_registry_discovers_all_mock_modules() -> None:
    registry = ModuleRegistry(real_root=Path("modules"), mock_root=Path("mock_modules"), use_mocks=True)
    discovered = registry.scan()
    assert set(discovered) == {ModuleId.MOISTURE, ModuleId.BOILING, ModuleId.AFTER_SALES}
    assert registry.get(ModuleId.MOISTURE).is_mock is True
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/unit/modules/test_registry.py -v`
Expected: FAIL because registry is missing.

- [ ] **Step 3: Implement registry**

```python
# core/modules/registry.py
import json
from dataclasses import dataclass
from pathlib import Path

from core.contracts.enums import ModuleId
from core.contracts.manifest import ModuleManifest
from core.contracts.validator import validate_module


@dataclass(frozen=True)
class RegisteredModule:
    manifest: ModuleManifest
    path: Path
    is_mock: bool


class ModuleRegistry:
    def __init__(self, real_root: Path, mock_root: Path, use_mocks: bool) -> None:
        self.real_root = real_root
        self.mock_root = mock_root
        self.use_mocks = use_mocks
        self._modules: dict[ModuleId, RegisteredModule] = {}

    def scan(self) -> dict[ModuleId, RegisteredModule]:
        self._modules.clear()
        roots = [(self.mock_root, True)] if self.use_mocks else [(self.real_root, False)]
        for root, is_mock in roots:
            if not root.exists():
                continue
            for module_dir in root.iterdir():
                if not module_dir.is_dir() or not validate_module(module_dir).ok:
                    continue
                manifest = ModuleManifest.model_validate(
                    json.loads((module_dir / "module.json").read_text(encoding="utf-8"))
                )
                self._modules[manifest.module_id] = RegisteredModule(manifest, module_dir.resolve(), is_mock)
        return dict(self._modules)

    def get(self, module_id: ModuleId) -> RegisteredModule:
        try:
            return self._modules[module_id]
        except KeyError as exc:
            raise KeyError(f"module not registered: {module_id}") from exc
```

Implement `healthcheck.py` with `run_healthcheck(module: RegisteredModule, timeout_ms: int = 10_000) -> tuple[bool, str]` using a short-lived `QProcess` and the module's `self-check` command.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/modules/test_registry.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add core/modules tests/unit/modules/test_registry.py
git commit -m "feat: discover registered modules"
```

### Task 4: Run modules with QProcess and typed progress events

**Files:**
- Create: `core/modules/process_runner.py`
- Create: `core/modules/progress_parser.py`
- Create: `tests/integration/test_process_runner.py`

**Interfaces:**
- Produces: `ModuleProcessRunner.start(module, job_path)`, signals `progress`, `completed`, `failed`, `cancelled`
- Consumes: `RegisteredModule`, `ProgressEvent`, `ModuleResult`

- [ ] **Step 1: Write failing pytest-qt integration test**

```python
# tests/integration/test_process_runner.py
import json
from pathlib import Path

from core.contracts.enums import ModuleId
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry


def test_runner_emits_progress_and_result(qtbot, tmp_path: Path) -> None:
    input_file = tmp_path / "normal.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / "output"
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps({
        "schema_version": "1.0", "job_id": "runner-001", "module_id": "moisture",
        "phase": "draft", "run_mode": "single", "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()), "module_config_file": None,
        "ai_enabled": False, "allowed_knowledge_scopes": ["shared", "moisture"]
    }), encoding="utf-8")
    registry = ModuleRegistry(Path("modules"), Path("mock_modules"), True)
    registry.scan()
    runner = ModuleProcessRunner(timeout_ms=10_000)
    with qtbot.waitSignal(runner.completed, timeout=15_000) as completed:
        runner.start(registry.get(ModuleId.MOISTURE), job_path)
    assert completed.args[0].status.value == "success"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/integration/test_process_runner.py -v`
Expected: FAIL because process runner is missing.

- [ ] **Step 3: Implement parser and runner**

```python
# core/modules/progress_parser.py
from core.contracts.progress import ProgressEvent


def parse_progress(line: bytes) -> ProgressEvent:
    return ProgressEvent.model_validate_json(line.decode("utf-8").strip())
```

```python
# core/modules/process_runner.py
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from core.contracts.job import JobRequest
from core.contracts.result import ModuleResult
from core.modules.progress_parser import parse_progress
from core.modules.registry import RegisteredModule


class ModuleProcessRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, timeout_ms: int = 120_000) -> None:
        super().__init__()
        self.timeout_ms = timeout_ms
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(lambda error: self.failed.emit(str(error)))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.job_path: Path | None = None

    def start(self, module: RegisteredModule, job_path: Path) -> None:
        self.job_path = job_path.resolve()
        entrypoint = module.path / module.manifest.entrypoint
        self.process.setWorkingDirectory(str(module.path))
        if entrypoint.suffix.lower() in {".bat", ".cmd"}:
            self.process.start("cmd.exe", ["/d", "/s", "/c", str(entrypoint), "run", "--job", str(self.job_path)])
        else:
            self.process.start(str(entrypoint), ["run", "--job", str(self.job_path)])
        self.timer.start(self.timeout_ms)

    def cancel(self) -> None:
        if self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(2_000):
                self.process.kill()
            self.cancelled.emit()

    def _read_stdout(self) -> None:
        while self.process.canReadLine():
            line = bytes(self.process.readLine())
            try:
                self.progress.emit(parse_progress(line))
            except Exception as exc:
                self.failed.emit(f"invalid progress event: {exc}")

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self.timer.stop()
        if self.job_path is None:
            self.failed.emit("runner lost job path")
            return
        job = JobRequest.model_validate_json(
            self.job_path.read_text(encoding="utf-8")
        )
        result_path = Path(job.output_dir) / "result.json"
        if exit_code != 0 or not result_path.is_file():
            error_text = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
            self.failed.emit(error_text or f"module exited with code {exit_code}")
            return
        try:
            self.completed.emit(ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8")))
        except Exception as exc:
            self.failed.emit(f"invalid result.json: {exc}")

    def _timeout(self) -> None:
        self.cancel()
        self.failed.emit("module timed out")
```

- [ ] **Step 4: Run process tests**

Run: `python -m pytest tests/integration/test_process_runner.py -v`
Expected: PASS and no desktop window is shown.

- [ ] **Step 5: Commit**

```powershell
git add core/modules tests/integration/test_process_runner.py
git commit -m "feat: run modules in isolated qprocess"
```

### Task 5: Build task snapshots, state machine, and orchestration

**Files:**
- Create: `core/tasks/__init__.py`
- Create: `core/tasks/models.py`
- Create: `core/tasks/snapshots.py`
- Create: `core/tasks/job_builder.py`
- Create: `core/tasks/service.py`
- Create: `tests/integration/test_task_service.py`

**Interfaces:**
- Produces: `TaskLifecycleState`, `TaskService.create_and_start()`, `TaskService.progress`, `TaskService.finished`, `TaskService.needs_confirmation`, `TaskService.failed`
- Consumes: `AppPaths`, `TaskRepository`, `ModuleRegistry`, `ModuleProcessRunner`

- [ ] **Step 1: Write failing task-service test**

```python
# tests/integration/test_task_service.py
from pathlib import Path

from core.contracts.enums import ModuleId
from core.tasks.service import TaskService


def test_task_service_snapshots_input_and_finishes(qtbot, app_services, tmp_path: Path) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"source-bytes")
    service = TaskService(
        paths=app_services["paths"],
        registry=app_services["registry"],
        task_repository=app_services["task_repository"],
    )
    with qtbot.waitSignal(service.finished, timeout=15_000) as signal:
        job_id = service.create_and_start(ModuleId.MOISTURE, [source])
    assert signal.args[0].status.value == "success"
    task = app_services["task_repository"].get(job_id)
    assert task["status"] == "success"
    assert source.read_bytes() == b"source-bytes"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/integration/test_task_service.py -v`
Expected: FAIL because task service and fixture are missing.

- [ ] **Step 3: Implement state, snapshot, builder, and service**

```python
# core/tasks/models.py
from enum import StrEnum


class TaskLifecycleState(StrEnum):
    CREATED = "created"
    RUNNING_DRAFT = "running_draft"
    WAITING_CONFIRMATION = "waiting_confirmation"
    RUNNING_FINALIZE = "running_finalize"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

```python
# core/tasks/snapshots.py
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Snapshot:
    source: Path
    copy: Path
    fingerprint: str


def snapshot_inputs(inputs: list[Path], task_dir: Path) -> list[Snapshot]:
    input_dir = task_dir / "inputs"
    input_dir.mkdir(parents=True, exist_ok=True)
    snapshots: list[Snapshot] = []
    for index, source in enumerate(inputs, start=1):
        data = source.read_bytes()
        target = input_dir / f"{index:03d}-{source.name}"
        target.write_bytes(data)
        snapshots.append(Snapshot(source.resolve(), target.resolve(), hashlib.sha256(data).hexdigest()))
    return snapshots
```

```python
# core/tasks/job_builder.py
from pathlib import Path

from core.contracts.enums import JobPhase, ModuleId, RunMode
from core.contracts.job import JobRequest


def build_draft_job(job_id: str, module_id: ModuleId, snapshots: list[Path], task_dir: Path) -> JobRequest:
    return JobRequest(
        schema_version="1.0",
        job_id=job_id,
        module_id=module_id,
        phase=JobPhase.DRAFT,
        run_mode=RunMode.SINGLE if len(snapshots) == 1 else RunMode.BATCH,
        input_files=[str(path.resolve()) for path in snapshots],
        output_dir=str((task_dir / "output-draft").resolve()),
        module_config_file=None,
        ai_enabled=False,
        allowed_knowledge_scopes=["shared", module_id.value],
    )
```

```python
# core/tasks/service.py
import itertools
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from core.contracts.enums import ModuleId, TaskStatus
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry
from core.platform.paths import AppPaths
from core.storage.repositories.tasks import TaskRepository
from core.tasks.job_builder import build_draft_job
from core.tasks.snapshots import snapshot_inputs


class TaskService(QObject):
    progress = Signal(str, object)
    finished = Signal(object)
    needs_confirmation = Signal(str, object)
    failed = Signal(str, str)

    _counter = itertools.count(1)

    def __init__(self, paths: AppPaths, registry: ModuleRegistry, task_repository: TaskRepository) -> None:
        super().__init__()
        self.paths = paths
        self.registry = registry
        self.task_repository = task_repository
        self.runners: dict[str, ModuleProcessRunner] = {}

    def create_and_start(self, module_id: ModuleId, inputs: list[Path]) -> str:
        timestamp = datetime.now().astimezone()
        job_id = f"{timestamp:%Y%m%d-%H%M%S}-{next(self._counter):03d}"
        task_dir = self.paths.tasks / job_id
        snapshots = snapshot_inputs(inputs, task_dir)
        job = build_draft_job(job_id, module_id, [item.copy for item in snapshots], task_dir)
        job_path = task_dir / "job-draft.json"
        job_path.parent.mkdir(parents=True, exist_ok=True)
        job_path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        self.task_repository.create(job_id, module_id.value, "running_draft", timestamp.isoformat())
        runner = ModuleProcessRunner()
        runner.progress.connect(lambda event: self.progress.emit(job_id, event))
        runner.completed.connect(lambda result: self._complete(job_id, result, job_path))
        runner.failed.connect(lambda message: self._fail(job_id, message))
        self.runners[job_id] = runner
        runner.start(self.registry.get(module_id), job_path)
        return job_id

    def _complete(self, job_id: str, result, job_path: Path) -> None:
        if result.status is TaskStatus.NEEDS_CONFIRMATION:
            job = JobRequest.model_validate_json(job_path.read_text(encoding="utf-8"))
            self.task_repository.update_status(job_id, "waiting_confirmation", result_path=str(Path(job.output_dir) / "result.json"))
            self.needs_confirmation.emit(job_id, result)
        else:
            job = JobRequest.model_validate_json(job_path.read_text(encoding="utf-8"))
            self.task_repository.update_status(job_id, result.status.value, result_path=str(Path(job.output_dir) / "result.json"))
            self.finished.emit(result)
        self.runners.pop(job_id, None)

    def _fail(self, job_id: str, message: str) -> None:
        self.task_repository.update_status(job_id, "failed", error=message)
        self.failed.emit(job_id, message)
        self.runners.pop(job_id, None)
```

Create `tests/conftest.py` fixture `app_services` that builds temporary paths, migrated database, repositories, and a mock-enabled registry, and returns exactly the keys `paths`, `registry`, `task_repository`, and `confirmation_repository`.

- [ ] **Step 4: Run task-service test**

Run: `python -m pytest tests/integration/test_task_service.py -v`
Expected: PASS; original bytes unchanged; task status success.

- [ ] **Step 5: Commit**

```powershell
git add core/tasks tests/conftest.py tests/integration/test_task_service.py
git commit -m "feat: orchestrate local module tasks"
```

### Task 6: Complete two-stage confirmation

**Files:**
- Create: `core/confirmations/__init__.py`
- Create: `core/confirmations/service.py`
- Modify: `core/tasks/service.py`
- Create: `tests/integration/test_confirmation_flow.py`

**Interfaces:**
- Produces: `ConfirmationService.submit(job_id, answers) -> Path`, `TaskService.finalize(job_id, bundle_path)`
- Consumes: `ConfirmationBundle`, `JobRequest`, `ModuleProcessRunner`

- [ ] **Step 1: Write failing confirmation-flow test**

```python
# tests/integration/test_confirmation_flow.py
from pathlib import Path

from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.enums import ModuleId
from core.confirmations.service import ConfirmationService
from core.tasks.service import TaskService


def test_confirmation_resubmits_and_finishes(qtbot, app_services, tmp_path: Path) -> None:
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"mock")
    task_service = TaskService(
        paths=app_services["paths"],
        registry=app_services["registry"],
        task_repository=app_services["task_repository"],
    )
    confirmation_service = ConfirmationService(app_services["paths"], app_services["confirmation_repository"])
    with qtbot.waitSignal(task_service.needs_confirmation, timeout=15_000) as waiting:
        job_id = task_service.create_and_start(ModuleId.MOISTURE, [source])
    result = waiting.args[1]
    bundle_path = confirmation_service.submit(
        job_id,
        result.confirmations,
        [ConfirmationAnswer(confirmation_id="mock-confirm-1", value="人工值")],
    )
    with qtbot.waitSignal(task_service.finished, timeout=15_000) as finished:
        task_service.finalize(job_id, bundle_path)
    assert finished.args[0].status.value == "success"
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/integration/test_confirmation_flow.py -v`
Expected: FAIL because confirmation service and finalize are missing.

- [ ] **Step 3: Implement confirmation service and finalize**

```python
# core/confirmations/service.py
from pathlib import Path

from core.contracts.confirmation import ConfirmationAnswer, ConfirmationBundle
from core.contracts.result import ConfirmationPrompt
from core.platform.paths import AppPaths
from core.storage.repositories.confirmations import ConfirmationRepository


class ConfirmationService:
    def __init__(self, paths: AppPaths, repository: ConfirmationRepository) -> None:
        self.paths = paths
        self.repository = repository

    def submit(self, job_id: str, prompts: list[ConfirmationPrompt], answers: list[ConfirmationAnswer]) -> Path:
        expected = {prompt.confirmation_id for prompt in prompts if prompt.blocking}
        supplied = {answer.confirmation_id for answer in answers}
        missing = expected - supplied
        if missing:
            raise ValueError(f"missing blocking confirmations: {sorted(missing)}")
        bundle = ConfirmationBundle(job_id=job_id, answers=answers)
        path = self.paths.tasks / job_id / "confirmation.json"
        path.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
        self.repository.save_answers(job_id, answers)
        return path
```

Add these imports and method to `TaskService`:

```python
from core.contracts.enums import JobPhase
from core.contracts.job import JobRequest

def finalize(self, job_id: str, bundle_path: Path) -> None:
    task_dir = self.paths.tasks / job_id
    draft_path = task_dir / "job-draft.json"
    draft = JobRequest.model_validate_json(draft_path.read_text(encoding="utf-8"))
    final_job = draft.model_copy(update={
        "phase": JobPhase.FINALIZE,
        "parent_job_id": job_id,
        "confirmation_file": str(bundle_path.resolve()),
        "output_dir": str((task_dir / "output-final").resolve()),
    })
    final_path = task_dir / "job-finalize.json"
    final_path.write_text(final_job.model_dump_json(indent=2), encoding="utf-8")
    self.task_repository.update_status(job_id, "running_finalize")
    runner = ModuleProcessRunner()
    runner.progress.connect(lambda event: self.progress.emit(job_id, event))
    runner.completed.connect(lambda result: self._complete(job_id, result, final_path))
    runner.failed.connect(lambda message: self._fail(job_id, message))
    self.runners[job_id] = runner
    runner.start(self.registry.get(draft.module_id), final_path)
```

This reuses `_complete()`, which must derive the result path from the `JobRequest.output_dir` rather than hard-coding `output-draft`.

- [ ] **Step 4: Run confirmation tests**

Run: `python -m pytest tests/integration/test_confirmation_flow.py -v`
Expected: PASS and final result path points to `output-final/result.json`.

- [ ] **Step 5: Commit**

```powershell
git add core/confirmations core/tasks/service.py tests/integration/test_confirmation_flow.py
git commit -m "feat: complete two-stage confirmation flow"
```

### Task 7: Build the PySide6 shell and approved visual theme

**Files:**
- Create: `app/__main__.py`
- Create: `app/bootstrap.py`
- Create: `ui/__init__.py`
- Create: `ui/page_ids.py`
- Create: `ui/main_window.py`
- Create: `ui/navigation.py`
- Create: `ui/styles/theme.py`
- Create: `assets/brand/team-logo.svg`
- Create: `resources/themes/bamboo.qss`
- Create: `tests/ui/test_main_window.py`

**Interfaces:**
- Produces: `create_application(data_root: Path | None) -> QApplication`, `MainWindow.navigate(PageId)`
- Consumes: services from Tasks 1-6

- [ ] **Step 1: Write failing window test**

```python
# tests/ui/test_main_window.py
from ui.main_window import MainWindow
from ui.page_ids import PageId


def test_main_window_has_canonical_navigation(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    assert window.windowTitle() == "竹简工作台"
    assert window.navigation.logo.objectName() == "teamLogo"
    assert window.navigation.logo.pixmap().isNull() is False
    assert list(window.pages) == [
        PageId.WORKBENCH,
        PageId.HISTORY,
        PageId.CONFIRMATIONS,
        PageId.KNOWLEDGE,
        PageId.SETTINGS,
    ]
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/ui/test_main_window.py -v`
Expected: FAIL because UI package is missing.

- [ ] **Step 3: Implement shell and theme**

```python
# ui/page_ids.py
from enum import StrEnum


class PageId(StrEnum):
    WORKBENCH = "workbench"
    HISTORY = "history"
    CONFIRMATIONS = "confirmations"
    KNOWLEDGE = "knowledge"
    SETTINGS = "settings"
```

```python
# ui/main_window.py
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QStackedWidget, QWidget

from ui.navigation import Navigation
from ui.page_ids import PageId


class MainWindow(QMainWindow):
    def __init__(self, context) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("竹简工作台")
        self.resize(1180, 760)
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        self.navigation = Navigation(context.resource_root / "assets" / "brand" / "team-logo.svg")
        self.stack = QStackedWidget()
        self.pages: dict[PageId, QWidget] = {
            PageId.WORKBENCH: QWidget(),
            PageId.HISTORY: QWidget(),
            PageId.CONFIRMATIONS: QWidget(),
            PageId.KNOWLEDGE: QWidget(),
            PageId.SETTINGS: QWidget(),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.navigation.page_selected.connect(self.navigate)

    def navigate(self, page_id: PageId) -> None:
        self.stack.setCurrentWidget(self.pages[page_id])
```

```python
# ui/navigation.py
from PySide6.QtCore import Signal
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ui.page_ids import PageId


class Navigation(QWidget):
    page_selected = Signal(object)

    def __init__(self, logo_path: Path) -> None:
        super().__init__()
        self.setObjectName("navigation")
        layout = QVBoxLayout(self)
        self.logo = QLabel("湖大智竹实践团队")
        self.logo.setObjectName("teamLogo")
        self.logo.setPixmap(QPixmap(str(logo_path)))
        self.logo.setScaledContents(True)
        self.logo.setFixedSize(150, 54)
        layout.addWidget(self.logo)
        for page_id, label in [
            (PageId.WORKBENCH, "工作台"),
            (PageId.HISTORY, "任务历史"),
            (PageId.CONFIRMATIONS, "待确认"),
            (PageId.KNOWLEDGE, "知识库"),
            (PageId.SETTINGS, "系统设置"),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, value=page_id: self.page_selected.emit(value))
            layout.addWidget(button)
        layout.addStretch()
```

Both `main_window.py` and `navigation.py` import `PageId` from `ui/page_ids.py`; neither imports the other for identifiers.

Create `assets/brand/team-logo.svg` as the approved A-style tender-green team mark on a transparent canvas. It must include the text `湖大智竹实践团队`, use `#2FA47D` and `#294D3C`, remain legible at 150×54 px, and contain no linked external bitmap or font. `app/bootstrap.py` sets `context.resource_root` to the repository root in development and PyInstaller's bundle root when frozen.

```css
/* resources/themes/bamboo.qss */
QMainWindow { background: #FBFAF4; color: #294D3C; }
#navigation { background: #294D3C; min-width: 190px; max-width: 190px; }
#navigation QPushButton { color: #BED3C7; border: 0; padding: 13px; text-align: left; border-radius: 10px; }
#navigation QPushButton:hover { background: #3A6651; color: white; }
QPushButton[primary="true"] { background: #2FA47D; color: white; padding: 10px 16px; border-radius: 10px; }
QFrame[card="true"] { background: #FFFDF8; border: 1px solid #DEDCCF; border-radius: 16px; }
QLabel[heading="true"] { color: #24386F; font-size: 22px; font-weight: 700; }
```

`app/bootstrap.py` builds temporary or default paths, database, repositories, registry, services, loads QSS, and returns an application context dataclass. `app/__main__.py` creates `QApplication`, `MainWindow`, shows it, and exits with `application.exec()`.

- [ ] **Step 4: Run UI test and smoke launch**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/ui/test_main_window.py -v
Remove-Item Env:QT_QPA_PLATFORM
python -m app
```

Expected: test PASS; visible app uses ivory background and dark bamboo navigation.

- [ ] **Step 5: Commit**

```powershell
git add app ui resources/themes tests/ui/test_main_window.py tests/conftest.py
git commit -m "feat: add BambooWorkbench desktop shell"
```

### Task 8: Add workbench, file intake, progress, confirmation, and result pages

**Files:**
- Create: `ui/pages/workbench_page.py`
- Create: `ui/pages/module_task_page.py`
- Create: `ui/pages/task_progress_page.py`
- Create: `ui/pages/confirmations_page.py`
- Create: `ui/pages/result_center_page.py`
- Create: `ui/widgets/module_card.py`
- Create: `ui/widgets/file_drop_zone.py`
- Create: `ui/widgets/output_files.py`
- Modify: `ui/main_window.py`
- Create: `tests/ui/test_mock_user_journey.py`

**Interfaces:**
- Produces: `ModuleSelected`, `TaskRequested`, `ConfirmationSubmitted` UI signals
- Consumes: `TaskService`, `ConfirmationService`, `ModuleResult`

- [ ] **Step 1: Write failing user-journey test**

```python
# tests/ui/test_mock_user_journey.py
from pathlib import Path

from PySide6.QtCore import Qt

from core.contracts.enums import ModuleId
from ui.main_window import MainWindow


def test_successful_mock_journey(qtbot, app_context, tmp_path: Path) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.show()
    workbench = window.workbench_page
    workbench.module_selected.emit(ModuleId.MOISTURE)
    task_page = window.module_task_page
    task_page.add_files([source])
    with qtbot.waitSignal(app_context.task_service.finished, timeout=15_000):
        qtbot.mouseClick(task_page.run_button, Qt.LeftButton)
    assert window.result_center_page.current_result.status.value == "success"
    assert window.result_center_page.output_buttons
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m pytest tests/ui/test_mock_user_journey.py -v`
Expected: FAIL because pages and signals do not exist.

- [ ] **Step 3: Implement focused pages**

```python
# ui/pages/workbench_page.py
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from core.contracts.enums import ModuleId
from ui.widgets.module_card import ModuleCard


class WorkbenchPage(QWidget):
    module_selected = Signal(object)

    def __init__(self, registry) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        company = QLabel("湖南桃花江竹材科技股份有限公司")
        company.setProperty("heading", True)
        layout.addWidget(company)
        layout.addWidget(QLabel("竹材品质数据智能工作台"))
        grid = QGridLayout()
        for column, (module_id, title) in enumerate([
            (ModuleId.MOISTURE, "原竹丝水分检测"),
            (ModuleId.BOILING, "水煮实验"),
            (ModuleId.AFTER_SALES, "售后统计"),
        ]):
            card = ModuleCard(module_id, title, registry)
            card.activated.connect(self.module_selected)
            grid.addWidget(card, 0, column)
        layout.addLayout(grid)
        layout.addStretch()
```

```python
# ui/pages/module_task_page.py
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget


class ModuleTaskPage(QWidget):
    task_requested = Signal(object, list)

    def __init__(self) -> None:
        super().__init__()
        self.module_id = None
        self.files: list[Path] = []
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.file_list = QListWidget()
        self.run_button = QPushButton("创建任务")
        self.run_button.setProperty("primary", True)
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.title)
        layout.addWidget(self.file_list)
        layout.addWidget(self.run_button)

    def set_module(self, module_id, title: str) -> None:
        self.module_id = module_id
        self.title.setText(title)

    def add_files(self, paths: list[Path]) -> None:
        for path in paths:
            resolved = path.resolve()
            if resolved not in self.files:
                self.files.append(resolved)
                self.file_list.addItem(str(resolved))

    def _run(self) -> None:
        if self.module_id is not None and self.files:
            self.task_requested.emit(self.module_id, list(self.files))
```

Implement the remaining pages with these exact public members:

- `TaskProgressPage.bind(job_id: str)` and `update_progress(event: ProgressEvent)`;
- `ConfirmationsPage.load(job_id: str, prompts: list[ConfirmationPrompt])` and signal `submitted(str, list[ConfirmationAnswer])`;
- `ResultCenterPage.show_result(result: ModuleResult)`, property `current_result`, and list `output_buttons`;
- `OutputFilesWidget.set_outputs(outputs: list[OutputArtifact])` using `QDesktopServices.openUrl(QUrl.fromLocalFile(path))`.

Wire page signals in `MainWindow`: module selection opens task page, task request starts `TaskService`, progress updates progress page, confirmation opens confirmation page, final result opens result center, and failures show a nonfatal message box.

- [ ] **Step 4: Run success and confirmation UI journeys**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/ui/test_mock_user_journey.py tests/integration/test_confirmation_flow.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```powershell
git add ui tests/ui/test_mock_user_journey.py
git commit -m "feat: complete unified mock task journey"
```

### Task 9: Add history, knowledge placeholder, settings, diagnostics, and fault UI

**Files:**
- Create: `ui/pages/history_page.py`
- Create: `ui/pages/knowledge_page.py`
- Create: `ui/pages/settings_page.py`
- Create: `core/platform/logging.py`
- Create: `core/platform/diagnostics.py`
- Modify: `ui/main_window.py`
- Create: `tests/ui/test_secondary_pages.py`
- Create: `tests/integration/test_fault_isolation.py`

**Interfaces:**
- Produces: read-only history table, knowledge placeholder API, settings persistence, log-directory action, fault-safe UI status
- Consumes: repositories, `SettingsStore`, `TaskService.failed`

- [ ] **Step 1: Write failing secondary-page and fault tests**

```python
# tests/ui/test_secondary_pages.py
from PySide6.QtCore import Qt


def test_settings_round_trip(qtbot, app_context, main_window) -> None:
    page = main_window.settings_page
    page.output_dir_edit.setText("D:/exports")
    qtbot.mouseClick(page.save_button, Qt.LeftButton)
    assert app_context.settings.get("output_dir") == "D:/exports"


def test_history_refreshes_from_repository(app_context, main_window) -> None:
    app_context.task_repository.create("history-1", "moisture", "success", "2026-07-13T10:00:00+08:00")
    main_window.history_page.refresh()
    assert main_window.history_page.table.rowCount() == 1
```

```python
# tests/integration/test_fault_isolation.py
from pathlib import Path

from core.contracts.enums import ModuleId


def test_crashed_module_does_not_close_application(qtbot, app_context, tmp_path: Path) -> None:
    source = tmp_path / "crash.xlsx"
    source.write_bytes(b"mock")
    with qtbot.waitSignal(app_context.task_service.failed, timeout=15_000):
        app_context.task_service.create_and_start(ModuleId.MOISTURE, [source])
    assert app_context.task_repository.list_recent(1)[0]["status"] == "failed"
```

- [ ] **Step 2: Run and verify failures**

Run: `python -m pytest tests/ui/test_secondary_pages.py tests/integration/test_fault_isolation.py -v`
Expected: FAIL because secondary pages and complete fault mapping are missing.

- [ ] **Step 3: Implement pages and diagnostics**

`HistoryPage` uses `QTableWidget`, calls `TaskRepository.list_recent()`, and provides `refresh()`. `KnowledgePage` displays four namespaces and the explicit message “模拟知识库：真实检索将在公共服务阶段接入”. `SettingsPage` contains `output_dir_edit`, `save_button`, and writes through `SettingsStore`. `logging.py` configures rotating UTF-8 application logs under `AppPaths.logs` and redacts strings matching `api_key`, `authorization`, and `bearer`. `diagnostics.py` returns application version, Python version, data root, registered modules, and log directory without secrets.

Add a `TaskService.cancel(job_id)` method that calls the active runner, persists `cancelled`, and emits a status signal. Ensure `_fail()` always persists the failure before notifying UI.

- [ ] **Step 4: Run all Plan 2 tests**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/unit/storage tests/unit/modules tests/integration tests/ui -v
python -m ruff check app core ui tests
```

Expected: all tests PASS; ruff exits 0.

- [ ] **Step 5: Commit**

```powershell
git add core/platform core/tasks ui tests
git commit -m "feat: add history settings and fault isolation"
```

## Plan 2 Completion Gate

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest tests/unit tests/integration tests/ui --cov=core --cov=ui -v
Remove-Item Env:QT_QPA_PLATFORM
python -m app
```

Manual smoke sequence:

1. Launch the approved BambooWorkbench shell.
2. Run a normal mock file through each module.
3. Run `confirm.xlsx`, answer the prompt, and open the final result.
4. Run `partial.xlsx`, `crash.xlsx`, and `invalid.xlsx`; verify the app stays open.
5. Open history and settings; verify local persistence after restart.

Expected: the full desktop framework works with mocks and no real business logic.
