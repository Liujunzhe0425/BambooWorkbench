# ruff: noqa: E402, I001

from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.confirmation_builder import build_confirmations
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import _confirmation_issues, _knowledge_requests
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_finalize_rebuilds_confirmation_ids_from_parent_not_current_id(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx", departments={"品质": 1}, moisture_values=(0.60,)
    )
    outcome = DeterministicPipeline().run((source,))
    issues = _confirmation_issues(outcome)

    draft = build_confirmations("draft-root", issues)
    rebuilt = build_confirmations("draft-root", issues)
    wrong = build_confirmations("finalize-current", issues)

    assert [item["confirmation_id"] for item in draft] == [
        item["confirmation_id"] for item in rebuilt
    ]
    assert [item["confirmation_id"] for item in draft] != [
        item["confirmation_id"] for item in wrong
    ]

    draft_job = JobRequest(
        "1.0",
        "draft-root",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (source,),
        tmp_path / "draft",
        allowed_knowledge_scopes=("moisture",),
    )
    finalize_job = JobRequest(
        "1.0",
        "finalize-current",
        ModuleId.MOISTURE,
        JobPhase.FINALIZE,
        RunMode.SINGLE,
        (source,),
        tmp_path / "final",
        allowed_knowledge_scopes=("moisture",),
        parent_job_id="draft-root",
    )
    assert (
        _knowledge_requests(draft_job, outcome)[0]["request_id"]
        == _knowledge_requests(finalize_job, outcome)[0]["request_id"]
    )
