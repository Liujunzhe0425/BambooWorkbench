# ruff: noqa: E402, I001

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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
    write_envelope,
)

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


@pytest.mark.parametrize("provider_status", ["ok-invalid", "denied", "error", "timeout", "missing"])
def test_invalid_denied_error_timeout_and_missing_all_preserve_orange(
    tmp_path: Path, workbook_factory, provider_status: str
) -> None:
    root = rule_root(tmp_path / "module", "high")
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", "high")
    draft_dir = tmp_path / "draft"
    assert run_draft(job(source, draft_dir, phase=JobPhase.DRAFT), pipeline(root)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    request = next(item for item in draft["service_requests"] if item["service"] == "ai")
    response_file = None
    if provider_status != "missing":
        status = "ok" if provider_status == "ok-invalid" else provider_status
        response = {
            "request_id": request["request_id"],
            "service": "ai",
            "status": status,
            "text": "MockProvider plain text" if status == "ok" else None,
            "error": "service unavailable" if status != "ok" else None,
        }
        response_file = write_envelope(tmp_path / "response.json", [response])

    final_dir = tmp_path / "final"
    assert (
        run_finalize(
            job(source, final_dir, phase=JobPhase.FINALIZE, service_file=response_file),
            pipeline(root),
        )
        == 0
    )
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert result["anomalies"][0]["severity"] == "info"
    assert result["confirmations"] == [] and result["service_requests"] == []
    assert workbook_contains_color(final_dir / "moisture_summary.xlsx", "orange")
    assert (final_dir / "analysis_report.md").is_file()
