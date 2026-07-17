# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtTest import QSignalSpy

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = REPO_ROOT / "modules" / "moisture"
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from core.contracts.enums import ModuleId
from core.modules.process_runner import ModuleProcessRunner
from core.modules.registry import ModuleRegistry
from moisture.application.deterministic_pipeline import DeterministicPipeline

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _slow_module(tmp_path: Path):
    registry = ModuleRegistry(
        REPO_ROOT / "modules", REPO_ROOT / "mock_modules", use_mocks=False
    )
    registry.scan()
    real = registry.get(ModuleId.MOISTURE)
    root = tmp_path / "slow-module"
    root.mkdir()
    helper = root / "slow.py"
    helper.write_text(
        """
import argparse, json, time
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('command')
parser.add_argument('--job', type=Path, required=True)
args = parser.parse_args()
job = json.loads(args.job.read_text(encoding='utf-8'))
output = Path(job['output_dir'])
output.mkdir(parents=True, exist_ok=True)
(output / '.partial.tmp').write_text('partial', encoding='utf-8')
print('{"type":"progress","percent":0,"message":"started"}', flush=True)
time.sleep(30)
""".strip(),
        encoding="utf-8",
    )
    launcher = root / "run_module.bat"
    launcher.write_text(
        '@echo off\r\n"%BAMBOO_MODULE_PYTHON%" "%~dp0slow.py" %*\r\n'
        "exit /b %ERRORLEVEL%\r\n",
        encoding="ascii",
    )
    return replace(real, path=root.resolve())


def _job(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "input.xlsx"
    source.write_bytes(b"synthetic")
    output = (tmp_path / "output").resolve()
    job = tmp_path / "job.json"
    job.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "t22-process",
                "module_id": "moisture",
                "phase": "draft",
                "run_mode": "single",
                "input_files": [str(source.resolve())],
                "output_dir": str(output),
            }
        ),
        encoding="utf-8",
    )
    return job.resolve(), output


def test_timeout_does_not_write_a_false_success_result(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BAMBOO_MODULE_PYTHON", sys.executable)
    job, output = _job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=100, cancellation_grace_ms=50)
    failed = QSignalSpy(runner.failed)

    runner.start(_slow_module(tmp_path), job)
    qtbot.waitUntil(lambda: failed.count() == 1, timeout=10_000)

    assert "timed out" in failed.at(0)[0]
    assert not (output / "result.json").exists()
    assert not runner.is_running


def test_cancel_does_not_write_a_false_success_result(
    qtbot, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("BAMBOO_MODULE_PYTHON", sys.executable)
    job, output = _job(tmp_path)
    runner = ModuleProcessRunner(timeout_ms=30_000, cancellation_grace_ms=50)
    cancelled = QSignalSpy(runner.cancelled)

    runner.start(_slow_module(tmp_path), job)
    qtbot.waitUntil(lambda: runner.is_running, timeout=5_000)
    assert runner.cancel() is True
    qtbot.waitUntil(lambda: cancelled.count() == 1, timeout=10_000)

    assert not (output / "result.json").exists()
    assert not runner.is_running


def test_bad_duplicate_and_temporary_inputs_are_file_isolated(
    tmp_path: Path, workbook_factory
) -> None:
    valid = workbook_factory(tmp_path / "valid.xlsx")
    before = valid.read_bytes()
    duplicate = tmp_path / "duplicate.xlsx"
    duplicate.write_bytes(before)
    temporary = tmp_path / "~$editing.xlsx"
    temporary.write_bytes(b"office lock")
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"bad workbook")

    outcome = DeterministicPipeline().run((valid, duplicate, temporary, corrupt))

    assert (outcome.processed_count, outcome.skipped_count, outcome.failed_count) == (1, 2, 1)
    assert [item["status"] for item in outcome.file_results] == [
        "success",
        "success",
        "success",
        "failed",
    ]
    assert valid.read_bytes() == before
