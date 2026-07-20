from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import run_draft
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


class KnowledgeOnlyPipeline:
    def run(self, input_files, *, default_year=None):
        outcome = DeterministicPipeline().run(input_files, default_year=default_year)
        values = {field: getattr(outcome, field) for field in outcome.__dataclass_fields__}
        values["pending_rule_matches"] = ()
        values["knowledge_guidance_needed"] = True
        return SimpleNamespace(**values)


def test_knowledge_only_request_preserves_success_and_contains_no_identity(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(tmp_path / "secret-supplier.xlsx", departments={"客户部门": 1})
    output = tmp_path / "output"
    job = JobRequest(
        "1.0",
        "draft-root",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (source,),
        output,
        allowed_knowledge_scopes=("shared", "moisture"),
    )

    assert run_draft(job, KnowledgeOnlyPipeline()) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert len(result["service_requests"]) == 1
    request_text = json.dumps(result["service_requests"][0], ensure_ascii=False)
    assert "secret-supplier" not in request_text
    assert "客户部门" not in request_text
    assert str(tmp_path) not in request_text
