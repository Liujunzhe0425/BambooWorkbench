# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.draft_orchestrator import run_draft
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_artifact_failure_registers_no_formal_output_and_cleans_temps(
    tmp_path: Path, workbook_factory, monkeypatch
) -> None:
    source = workbook_factory(tmp_path / "source.xlsx")
    output = tmp_path / "output"
    job = JobRequest(
        "1.0",
        "t22-artifact-failure",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (source,),
        output,
    )
    import moisture.application.draft_orchestrator as orchestrator

    def fail_markdown(*_args, **_kwargs):
        raise OSError("synthetic writer failure")

    monkeypatch.setattr(orchestrator, "write_analysis_markdown", fail_markdown)

    assert run_draft(job) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "failed"
    assert result["outputs"] == []
    assert not (output / "moisture_summary.xlsx").exists()
    assert not (output / "analysis_report.md").exists()
    assert not list(output.glob(".*.tmp"))
    assert not list(output.glob(".moisture_summary-*.xlsx"))


def test_result_json_is_the_last_atomic_replace(
    tmp_path: Path, workbook_factory, monkeypatch
) -> None:
    source = workbook_factory(tmp_path / "source.xlsx")
    output = tmp_path / "output"
    job = JobRequest(
        "1.0",
        "t22-result-last",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (source,),
        output,
    )
    import os

    replacements: list[str] = []
    real_replace = os.replace

    def record_replace(source_path, destination_path):
        replacements.append(Path(destination_path).name)
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(os, "replace", record_replace)

    assert run_draft(job) == 0

    assert replacements[-1] == "result.json"
    assert (output / "moisture_summary.xlsx").is_file()
    assert (output / "analysis_report.md").is_file()
    assert (output / "result.json").is_file()
