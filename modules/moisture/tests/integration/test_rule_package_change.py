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
    valid_ai_response,
    workbook_contains_color,
    write_envelope,
)

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_changed_rule_hash_cannot_apply_stale_response(tmp_path: Path, workbook_factory) -> None:
    draft_root = rule_root(tmp_path / "draft-module", "high", marker="v1")
    final_root = rule_root(tmp_path / "final-module", "high", marker="v2")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    draft_dir = tmp_path / "draft"
    assert run_draft(job(source, draft_dir, phase=JobPhase.DRAFT), pipeline(draft_root)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    request = next(item for item in draft["service_requests"] if item["service"] == "ai")
    response_file = write_envelope(tmp_path / "response.json", [valid_ai_response(request)])

    final_dir = tmp_path / "final"
    assert (
        run_finalize(
            job(source, final_dir, phase=JobPhase.FINALIZE, service_file=response_file),
            pipeline(final_root),
        )
        == 0
    )
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert result["anomalies"][0]["severity"] == "info"
    assert workbook_contains_color(final_dir / "moisture_summary.xlsx", "orange")
    assert any("SERVICE_RESPONSE_DEGRADED" in error for error in result["errors"])
