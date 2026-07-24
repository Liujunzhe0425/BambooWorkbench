from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.adapters.rules.local_editable_repository import (  # noqa: E402
    LocalEditableRuleRepository,
)
from moisture.application.draft_orchestrator import run_draft  # noqa: E402
from moisture.contract.job_models import (  # noqa: E402
    JobPhase,
    JobRequest,
    ModuleId,
    RunMode,
)

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _summary(tmp_path: Path, workbook_factory) -> Path:
    source = workbook_factory(
        tmp_path / "source.xlsx",
        moisture_values=(0.60,),
        mass_values=((100, 40, 0),),
        supplier="脱敏供应商",
        material_type="原竹丝",
        arrival_date="2026-07-01",
        test_date="2026-07-02",
    )
    output = tmp_path / "summary"
    job = JobRequest(
        "1.0",
        "rule-preview-summary",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.SINGLE,
        (source,),
        output,
    )
    assert run_draft(job) == 0
    return output / "moisture_summary.xlsx"


def test_preview_reuses_standard_summary_reader_and_current_evaluator(
    tmp_path: Path, workbook_factory
) -> None:
    summary = _summary(tmp_path, workbook_factory)
    repository = LocalEditableRuleRepository(tmp_path / "managed-rules")
    manifest = {
        "schema_version": "1.0",
        "package_id": "preview-v1",
        "rule_version": "preview-v1",
        "rules_file": "rules.yaml",
        "rules_sha256": "0" * 64,
        "source": "synthetic preview",
        "applicable_scope": "原竹丝；全年",
        "customer_confirmation_status": "confirmed",
        "released_at": "2026-07-24T00:00:00+08:00",
        "module_version": "1.0.1",
    }
    rules = """definitions:
  - rule_id: PREVIEW_HIGH_A
    rule_type: numeric_threshold
    field: total_average
    operator: ">"
    threshold: "0.55"
    color: orange
    applicable_materials: [原竹丝]
    applicable_seasons: [all]
    customer_confirmation_status: confirmed
  - rule_id: PREVIEW_HIGH_B
    rule_type: numeric_threshold
    field: total_average
    operator: ">"
    threshold: "0.58"
    color: orange
    applicable_materials: [原竹丝]
    applicable_seasons: [all]
    customer_confirmation_status: confirmed
"""
    repository.create_draft(manifest, rules)

    preview = repository.preview_draft("preview-v1", (summary,))

    assert preview.batch_count == 1
    assert preview.matched_batch_count == 1
    assert preview.decision_count == 2
    assert preview.pending_match_count == 0
    assert preview.warnings == (
        "threshold_conflict:PREVIEW_HIGH_A:PREVIEW_HIGH_B",
    )
