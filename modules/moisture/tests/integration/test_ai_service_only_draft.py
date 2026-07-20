from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import run_draft
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode
from moisture.domain.review import AIReviewCandidate

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


class AIOnlyPipeline:
    def run(self, input_files, *, default_year=None):
        outcome = DeterministicPipeline().run(input_files, default_year=default_year)
        values = {field: getattr(outcome, field) for field in outcome.__dataclass_fields__}
        values["pending_rule_matches"] = ()
        values["ai_review_candidates"] = (
            AIReviewCandidate(
                "candidate-1", "total_average", Decimal("0.61"), Decimal("0.55"), Decimal("0.109")
            ),
        )
        return SimpleNamespace(**values)


def test_ai_enabled_false_still_declares_one_consent_gated_request(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(tmp_path / "source.xlsx", departments={"品质": 1})
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
            ai_enabled=False,
        )
        assert run_draft(job, AIOnlyPipeline()) == 0

    first = json.loads((first_dir / "result.json").read_text(encoding="utf-8"))
    second = json.loads((second_dir / "result.json").read_text(encoding="utf-8"))
    assert first["status"] == "success"
    assert len(first["service_requests"]) == 1
    assert first["service_requests"][0]["service"] == "ai"
    assert first["service_requests"][0]["request_id"] == second["service_requests"][0]["request_id"]
