from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from decimal import Decimal
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import run_draft
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _job(source: Path, output: Path, job_id: str = "draft-root") -> JobRequest:
    return JobRequest(
        "1.0", job_id, ModuleId.MOISTURE, JobPhase.DRAFT, RunMode.SINGLE, (source,), output
    )


def test_formula_conflict_confirmation_is_repeatable(tmp_path: Path, workbook_factory) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx",
        departments={"品质": 1},
        moisture_formula_cached_values=[0.1],
    )
    first_dir, second_dir = tmp_path / "first", tmp_path / "second"

    assert run_draft(_job(source, first_dir), DeterministicPipeline()) == 0
    assert run_draft(_job(source, second_dir), DeterministicPipeline()) == 0
    first = json.loads((first_dir / "result.json").read_text(encoding="utf-8"))
    second = json.loads((second_dir / "result.json").read_text(encoding="utf-8"))

    assert first["status"] == "needs_confirmation"
    assert any(item["field"] == "sample_1" for item in first["confirmations"])
    assert [item["confirmation_id"] for item in first["confirmations"]] == [
        item["confirmation_id"] for item in second["confirmations"]
    ]


def test_reliable_excel_value_does_not_prompt(tmp_path: Path, workbook_factory) -> None:
    source = workbook_factory(tmp_path / "matched.xlsx", departments={"品质": 1})
    output = tmp_path / "output"

    assert run_draft(_job(source, output)) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert all(item["field"] != "sample_1" for item in result["confirmations"])


def test_excel_rounding_tail_within_formula_tolerance_does_not_prompt(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "rounded.xlsx",
        departments={"品质": 1},
        moisture_formula_cached_values=[Decimal("0.494845360824742")],
    )
    output = tmp_path / "output"

    assert run_draft(_job(source, output)) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))

    assert result["status"] == "success"
    assert result["confirmations"] == []
