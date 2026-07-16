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
    valid_ai_response,
    workbook_contains_color,
    write_envelope,
)

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


@pytest.mark.parametrize(("direction", "color"), [("high", "red"), ("low", "blue")])
def test_valid_structured_ai_response_promotes_red_or_blue(
    tmp_path: Path, workbook_factory, direction: str, color: str
) -> None:
    root = rule_root(tmp_path / "module", direction)
    source = governed_workbook(workbook_factory, tmp_path / "source.xlsx", direction)
    draft_dir = tmp_path / "draft"
    assert run_draft(job(source, draft_dir, phase=JobPhase.DRAFT), pipeline(root)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    ai_request = next(item for item in draft["service_requests"] if item["service"] == "ai")
    response_file = write_envelope(
        tmp_path / "service-response.json", [valid_ai_response(ai_request)]
    )

    final_dir = tmp_path / "final"
    assert (
        run_finalize(
            job(source, final_dir, phase=JobPhase.FINALIZE, service_file=response_file),
            pipeline(root),
        )
        == 0
    )
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))

    assert result["job_id"] == "finalize-current"
    assert result["status"] == "success"
    assert result["confirmations"] == [] and result["service_requests"] == []
    assert result["anomalies"][0]["severity"] == "warning"
    assert "非正式错误或责任结论" in result["anomalies"][0]["message"]
    assert workbook_contains_color(final_dir / "moisture_summary.xlsx", color)
