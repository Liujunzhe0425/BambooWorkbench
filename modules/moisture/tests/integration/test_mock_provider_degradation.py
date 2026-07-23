# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.draft_orchestrator import run_draft
from moisture.application.finalize_orchestrator import run_finalize
from moisture.contract.job_models import JobPhase
from integration.t19_helpers import (
    governed_workbook,
    job,
    pipeline,
    rule_root,
    workbook_contains_color,
)

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_summary_flow_is_independent_of_ai_provider(tmp_path: Path, workbook_factory) -> None:
    root = rule_root(tmp_path / "module", "high")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    draft_dir = tmp_path / "draft"
    assert run_draft(job(source, draft_dir, phase=JobPhase.DRAFT), pipeline(root)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    assert not any(item["service"] == "ai" for item in draft["service_requests"])

    final_dir = tmp_path / "final"
    assert run_finalize(job(source, final_dir, phase=JobPhase.FINALIZE), pipeline(root)) == 0
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert result["confirmations"] == [] and result["service_requests"] == []
    assert workbook_contains_color(final_dir / "moisture_summary.xlsx", "orange")
    assert not any("ai_" in error.lower() for error in result["errors"])
