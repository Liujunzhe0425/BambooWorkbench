# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtTest import QSignalSpy

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "modules" / "moisture"
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from core.contracts.enums import ModuleId
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _real_module():
    registry = ModuleRegistry(
        REPO_ROOT / "modules", REPO_ROOT / "mock_modules", use_mocks=False
    )
    discovered = registry.scan()
    return registry, discovered[ModuleId.MOISTURE]


def test_real_registry_discovers_and_health_checks_formal_module() -> None:
    registry, module = _real_module()

    assert module.path == MODULE_ROOT.resolve()
    assert module.is_mock is False
    assert registry.get(ModuleId.MOISTURE).health == "healthy"
    healthy, detail = registry.check_health(ModuleId.MOISTURE)
    assert healthy is True
    assert detail == "ok"


def test_real_runner_accepts_progress_result_and_existing_outputs(
    qtbot, tmp_path: Path, workbook_factory
) -> None:
    _, module = _real_module()
    source = workbook_factory(tmp_path / "inputs" / "source.xlsx")
    output_dir = (tmp_path / "output").resolve()
    job_path = tmp_path / "jobs" / "job.json"
    job_path.parent.mkdir(parents=True)
    job_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "t21-real-runner",
                "module_id": "moisture",
                "phase": "draft",
                "run_mode": "single",
                "input_files": [str(source.resolve())],
                "output_dir": str(output_dir),
                "ai_enabled": False,
                "allowed_knowledge_scopes": [],
            }
        ),
        encoding="utf-8",
    )
    runner = ModuleProcessRunner(timeout_ms=30_000)
    progress = QSignalSpy(runner.progress)
    completed = QSignalSpy(runner.completed)
    failed = QSignalSpy(runner.failed)

    runner.start(module, job_path.resolve())
    qtbot.waitUntil(lambda: completed.count() + failed.count() == 1, timeout=30_000)

    assert failed.count() == 0
    result = completed.at(0)[0]
    assert result.job_id == "t21-real-runner"
    assert [progress.at(index)[0].percent for index in range(progress.count())] == [0, 100]
    assert {Path(item.path).name for item in result.outputs} == {
        "moisture_summary.xlsx",
        "analysis_report.md",
    }
    assert all(Path(item.path).is_file() for item in result.outputs)
    assert (output_dir / "result.json").is_file()
