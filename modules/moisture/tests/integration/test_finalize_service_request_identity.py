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
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _job(source: Path, output: Path, *, phase: JobPhase, confirmation: Path | None = None):
    return JobRequest(
        "1.0",
        "month-day-root" if phase is JobPhase.DRAFT else "month-day-final",
        ModuleId.MOISTURE,
        phase,
        RunMode.SINGLE,
        (source,),
        output,
        parent_job_id="month-day-root" if phase is JobPhase.FINALIZE else None,
        confirmation_file=confirmation,
    )


def test_year_confirmation_finalize_has_no_ai_request_or_response_dependency(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="4.8",
        test_date="4.9",
    )
    draft_dir = tmp_path / "draft"
    assert run_draft(_job(source, draft_dir, phase=JobPhase.DRAFT)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    assert [item["field"] for item in draft["confirmations"]] == ["default_year"]
    assert not any(item["service"] == "ai" for item in draft["service_requests"])

    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "month-day-root",
                "answers": [
                    {
                        "confirmation_id": draft["confirmations"][0]["confirmation_id"],
                        "value": "2026",
                        "apply_to_batch": True,
                        "remember_mapping": False,
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    final_dir = tmp_path / "final"
    assert (
        run_finalize(_job(source, final_dir, phase=JobPhase.FINALIZE, confirmation=confirmation))
        == 0
    )
    final = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))
    assert final["job_id"] == "month-day-final"
    assert final["status"] == "success"
    assert final["confirmations"] == []
    assert final["service_requests"] == []
    assert not any("ai_" in error.lower() for error in final["errors"])
