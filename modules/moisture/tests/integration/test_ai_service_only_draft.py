from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.draft_orchestrator import run_draft
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_summary_draft_never_declares_ai_review_request(tmp_path: Path, workbook_factory) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
    )
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"

    for output in (first_dir, second_dir):
        job = JobRequest(
            "1.0",
            "draft-root",
            ModuleId.MOISTURE,
            JobPhase.DRAFT,
            RunMode.SINGLE,
            (source,),
            output,
            ai_enabled=True,
        )
        assert run_draft(job) == 0

    first = json.loads((first_dir / "result.json").read_text(encoding="utf-8"))
    second = json.loads((second_dir / "result.json").read_text(encoding="utf-8"))
    assert first["status"] in {"success", "needs_confirmation"}
    assert not any(item["service"] == "ai" for item in first["service_requests"])
    assert first["service_requests"] == second["service_requests"]
