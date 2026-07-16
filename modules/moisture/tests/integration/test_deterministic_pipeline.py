from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.deterministic_pipeline import DeterministicPipeline  # noqa: E402

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_single_file_runs_formula_statistics_and_pending_rules(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx", departments={"品质": 2}, moisture_values=(0.60, 0.61)
    )

    outcome = DeterministicPipeline().run((source,))

    assert outcome.processed_count == 1
    assert outcome.failed_count == 0
    assert outcome.skipped_count == 0
    assert outcome.batches[0].statistics.sample_count == 2
    assert outcome.batches[0].final_display_color.value == "none"
    assert outcome.batches[0].screening_decision.status.value == "normal"
    assert outcome.pending_rule_matches
