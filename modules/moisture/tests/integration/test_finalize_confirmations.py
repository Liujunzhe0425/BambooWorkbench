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
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _job(
    source: Path, output: Path, *, phase: JobPhase, confirmation: Path | None = None
) -> JobRequest:
    return JobRequest(
        "1.0",
        "draft-root" if phase is JobPhase.DRAFT else "finalize-current",
        ModuleId.MOISTURE,
        phase,
        RunMode.SINGLE,
        (source,),
        output,
        parent_job_id="draft-root" if phase is JobPhase.FINALIZE else None,
        confirmation_file=confirmation,
    )


def test_finalize_replays_formula_and_rule_answers_then_emits_no_follow_up(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx",
        departments={"品质": 1},
        moisture_formula_cached_values=[0.1],
    )
    draft_dir = tmp_path / "draft"
    assert run_draft(_job(source, draft_dir, phase=JobPhase.DRAFT)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    answers = [
        {
            "confirmation_id": prompt["confirmation_id"],
            "value": prompt["options"][0],
            "apply_to_batch": False,
            "remember_mapping": False,
        }
        for prompt in draft["confirmations"]
    ]
    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(
        json.dumps(
            {"schema_version": "1.0", "job_id": "draft-root", "answers": answers},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    final_dir = tmp_path / "final"
    assert (
        run_finalize(_job(source, final_dir, phase=JobPhase.FINALIZE, confirmation=confirmation))
        == 0
    )
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))
    assert result["job_id"] == "finalize-current"
    assert result["confirmations"] == []
    assert result["service_requests"] == []
    assert result["status"] == "success"


def test_required_confirmation_missing_or_invalid_answer_is_legal_failure(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx", departments={"品质": 1}, moisture_values=(0.60,)
    )
    missing_dir = tmp_path / "missing"
    assert run_finalize(_job(source, missing_dir, phase=JobPhase.FINALIZE)) == 0
    missing = json.loads((missing_dir / "result.json").read_text(encoding="utf-8"))
    assert missing["status"] == "failed"
    assert missing["errors"] == ["CONFIRMATION_PROTOCOL_INVALID"]


def test_finalize_rejects_wrong_candidate_type_and_illegal_batch_flag(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx",
        departments={"品质": 1},
        moisture_formula_cached_values=[0.1],
    )
    draft_dir = tmp_path / "draft"
    assert run_draft(_job(source, draft_dir, phase=JobPhase.DRAFT)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    formula = next(item for item in draft["confirmations"] if item["field"] == "sample_1")
    answers = [
        {
            "confirmation_id": prompt["confirmation_id"],
            "value": (1 if prompt is formula else prompt["options"][0]),
            "apply_to_batch": (prompt is formula),
            "remember_mapping": False,
        }
        for prompt in draft["confirmations"]
    ]
    confirmation = tmp_path / "invalid-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {"schema_version": "1.0", "job_id": "draft-root", "answers": answers},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    output = tmp_path / "final"
    assert (
        run_finalize(_job(source, output, phase=JobPhase.FINALIZE, confirmation=confirmation)) == 0
    )
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["errors"] == ["CONFIRMATION_ANSWER_INVALID"]


def test_confirmation_file_is_optional_when_rebuild_has_no_prompts(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(tmp_path / "source.xlsx", departments={"品质": 1})

    class NoPromptPipeline:
        def run(self, input_files, *, default_year=None):
            outcome = (
                __import__(
                    "moisture.application.deterministic_pipeline",
                    fromlist=["DeterministicPipeline"],
                )
                .DeterministicPipeline()
                .run(input_files, default_year=default_year)
            )
            from dataclasses import replace

            return replace(outcome, pending_rule_matches=())

    output = tmp_path / "final"
    assert run_finalize(_job(source, output, phase=JobPhase.FINALIZE), NoPromptPipeline()) == 0
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"


def test_one_default_year_answer_replays_a_month_day_batch(
    tmp_path: Path, workbook_factory
) -> None:
    sources = tuple(
        workbook_factory(
            tmp_path / f"source-{index}.xlsx",
            departments={"品质": count},
            arrival_date="4月8日",
            test_date="4月9日",
        )
        for index, count in ((1, 6), (2, 8))
    )
    draft_job = JobRequest(
        "1.0",
        "year-draft-root",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.BATCH,
        sources,
        tmp_path / "year-draft",
    )
    assert run_draft(draft_job) == 0
    draft = json.loads((tmp_path / "year-draft" / "result.json").read_text(encoding="utf-8"))
    assert draft["status"] == "needs_confirmation"
    assert draft["summary"]["processed_count"] == 2
    assert [item["field"] for item in draft["confirmations"]] == ["default_year"]

    confirmation = tmp_path / "year-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "year-draft-root",
                "answers": [
                    {
                        "confirmation_id": draft["confirmations"][0]["confirmation_id"],
                        "value": "2026",
                        "apply_to_batch": True,
                        "remember_mapping": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    final_job = JobRequest(
        "1.0",
        "year-finalize-current",
        ModuleId.MOISTURE,
        JobPhase.FINALIZE,
        RunMode.BATCH,
        sources,
        tmp_path / "year-final",
        parent_job_id="year-draft-root",
        confirmation_file=confirmation,
    )

    assert run_finalize(final_job) == 0
    result = json.loads((tmp_path / "year-final" / "result.json").read_text(encoding="utf-8"))
    assert result["job_id"] == "year-finalize-current"
    assert result["status"] == "success"
    assert result["summary"]["processed_count"] == 2
    assert result["confirmations"] == []
    assert result["service_requests"] == []


def test_multiple_yearless_files_require_batch_application(
    tmp_path: Path, workbook_factory
) -> None:
    sources = tuple(
        workbook_factory(
            tmp_path / f"batch-{index}.xlsx",
            arrival_date="4月8日",
            test_date="4月9日",
            moisture_values=(0.50 + index * 0.01,),
        )
        for index in range(2)
    )
    draft_dir = tmp_path / "batch-draft"
    draft_job = JobRequest(
        "1.0",
        "batch-year-root",
        ModuleId.MOISTURE,
        JobPhase.DRAFT,
        RunMode.BATCH,
        sources,
        draft_dir,
    )
    assert run_draft(draft_job) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    confirmation = tmp_path / "batch-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "batch-year-root",
                "answers": [
                    {
                        "confirmation_id": draft["confirmations"][0]["confirmation_id"],
                        "value": "2026",
                        "apply_to_batch": False,
                        "remember_mapping": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    final_dir = tmp_path / "batch-final"
    final_job = JobRequest(
        "1.0",
        "batch-year-final",
        ModuleId.MOISTURE,
        JobPhase.FINALIZE,
        RunMode.BATCH,
        sources,
        final_dir,
        parent_job_id="batch-year-root",
        confirmation_file=confirmation,
    )

    assert run_finalize(final_job) == 0
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["errors"] == ["CONFIRMATION_ANSWER_INVALID"]


@pytest.mark.parametrize("value", ("", "202", "2026年", "1899", "2101", True, 2026.0))
def test_default_year_confirmation_rejects_invalid_values(
    tmp_path: Path, workbook_factory, value: object
) -> None:
    source = workbook_factory(
        tmp_path / "invalid-year.xlsx",
        arrival_date="4月8日",
        test_date="4月9日",
    )
    draft_dir = tmp_path / "invalid-year-draft"
    assert run_draft(_job(source, draft_dir, phase=JobPhase.DRAFT)) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    confirmation = tmp_path / "invalid-year-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "draft-root",
                "answers": [
                    {
                        "confirmation_id": draft["confirmations"][0]["confirmation_id"],
                        "value": value,
                        "apply_to_batch": True,
                        "remember_mapping": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    output = tmp_path / f"invalid-year-final-{str(value).replace('.', '_')}"

    assert (
        run_finalize(_job(source, output, phase=JobPhase.FINALIZE, confirmation=confirmation)) == 0
    )
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["errors"] == ["CONFIRMATION_ANSWER_INVALID"]
