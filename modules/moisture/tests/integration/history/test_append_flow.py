"""Representative draft/finalize paths for standard-summary append."""

from __future__ import annotations

# ruff: noqa: E402, I001

import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.adapters.history.summary_reader import StandardSummaryReader
from moisture.application.draft_orchestrator import run_draft
from moisture.application.finalize_orchestrator import run_finalize
from moisture.contract.job_models import JobPhase, JobRequest, ModuleId, RunMode
from moisture.infrastructure.hashing import sha256_file

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _job(
    inputs: tuple[Path, ...],
    output_dir: Path,
    config: Path,
    *,
    phase: JobPhase = JobPhase.DRAFT,
    confirmation_file: Path | None = None,
) -> JobRequest:
    return JobRequest(
        schema_version="1.0",
        job_id="append-root" if phase is JobPhase.DRAFT else "append-final",
        module_id=ModuleId.MOISTURE,
        phase=phase,
        run_mode=RunMode.BATCH,
        input_files=inputs,
        output_dir=output_dir,
        module_config_file=config,
        parent_job_id="append-root" if phase is JobPhase.FINALIZE else None,
        confirmation_file=confirmation_file,
    )


def _append_config(tmp_path: Path) -> Path:
    config = tmp_path / "append-config.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "operation": "append_summary",
                "inputs": [
                    {"role": "base_summary", "input_index": 0},
                    {"role": "new_raw", "input_index": 1},
                ],
            }
        ),
        encoding="utf-8",
    )
    return config


def _base_summary(source: Path, output_dir: Path) -> Path:
    job = JobRequest(
        schema_version="1.0",
        job_id="base-summary",
        module_id=ModuleId.MOISTURE,
        phase=JobPhase.DRAFT,
        run_mode=RunMode.SINGLE,
        input_files=(source,),
        output_dir=output_dir,
    )
    assert run_draft(job) == 0
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    return output_dir / "moisture_summary.xlsx"


def test_append_preserves_history_adds_new_batch_and_keeps_inputs_unchanged(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old-batch.xlsx",
        moisture_values=(0.50, 0.51),
        mass_values=((100, 50, 0), (100, 49, 0)),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    new_raw = workbook_factory(
        tmp_path / "new-batch.xlsx",
        moisture_values=(0.52, 0.53),
        mass_values=((100, 48, 0), (100, 47, 0)),
        arrival_date="2026-04-10",
        test_date="2026-04-11",
    )
    before = {path: sha256_file(path) for path in (base, new_raw)}
    original = StandardSummaryReader().read(base).batches[0]
    output = tmp_path / "append-output"

    assert run_draft(_job((base, new_raw), output, _append_config(tmp_path))) == 0

    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["summary"] == {
        "input_count": 2,
        "processed_count": 2,
        "skipped_count": 0,
        "failed_count": 0,
        "anomaly_count": 0,
        "confirmation_count": 0,
    }
    appended = StandardSummaryReader().read(output / "moisture_summary.xlsx")
    assert [batch.record.record_id for batch in appended.batches] == [
        "old-batch",
        "new-batch",
    ]
    assert appended.batches[0].record.samples == original.record.samples
    assert appended.batches[0].statistics == original.statistics
    assert appended.batches[0].rule_hash == original.rule_hash
    assert appended.batches[0].rule_confirmation_status == "confirmed"
    assert [batch.record.test_date.isoformat() for batch in appended.batches] == [
        "2026-04-09",
        "2026-04-11",
    ]
    assert {path: sha256_file(path) for path in (base, new_raw)} == before


def test_append_skips_source_sha_already_present_in_history(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old" / "original.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    duplicate = tmp_path / "new" / "copy.xlsx"
    duplicate.parent.mkdir(parents=True)
    shutil.copyfile(old_raw, duplicate)
    output = tmp_path / "duplicate-output"

    assert run_draft(_job((base, duplicate), output, _append_config(tmp_path))) == 0

    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["summary"]["processed_count"] == 1
    assert result["summary"]["skipped_count"] == 1
    assert result["file_results"][1]["error"].startswith("DUPLICATE_HISTORY_SOURCE")
    snapshot = StandardSummaryReader().read(output / "moisture_summary.xlsx")
    assert len(snapshot.batches) == 1


def test_append_skips_same_record_and_business_values_with_different_file_sha(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old" / "same-batch.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    same_business = workbook_factory(
        tmp_path / "new" / "same-batch.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    workbook = load_workbook(same_business)
    workbook.active["Z50"] = "不影响业务内容的文件差异"
    workbook.save(same_business)
    workbook.close()
    assert sha256_file(old_raw) != sha256_file(same_business)
    output = tmp_path / "record-duplicate-output"

    assert run_draft(_job((base, same_business), output, _append_config(tmp_path))) == 0

    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["summary"]["processed_count"] == 1
    assert result["summary"]["skipped_count"] == 1
    assert result["file_results"][1]["error"].startswith("DUPLICATE_HISTORY_RECORD")
    assert result["confirmations"] == []


def test_append_conflict_rebuilds_same_id_and_use_new_applies_only_to_new_output(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old" / "same-batch.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    new_raw = workbook_factory(
        tmp_path / "new" / "same-batch.xlsx",
        moisture_values=(0.52,),
        mass_values=((100, 48, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    config = _append_config(tmp_path)
    draft_output = tmp_path / "draft-output"

    assert run_draft(_job((base, new_raw), draft_output, config)) == 0

    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    assert draft["status"] == "needs_confirmation"
    assert len(draft["confirmations"]) == 1
    prompt = draft["confirmations"][0]
    assert prompt["field"] == "history_record_conflict"
    assert prompt["options"] == ["keep_existing", "use_new"]
    draft_batch = StandardSummaryReader().read(draft_output / "moisture_summary.xlsx").batches[0]
    assert draft_batch.statistics.mean == original_mean(base)

    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "append-root",
                "answers": [
                    {
                        "confirmation_id": prompt["confirmation_id"],
                        "value": "use_new",
                        "apply_to_batch": False,
                        "remember_mapping": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "final-output"
    assert (
        run_finalize(
            _job(
                (base, new_raw),
                final_output,
                config,
                phase=JobPhase.FINALIZE,
                confirmation_file=confirmation,
            )
        )
        == 0
    )

    final = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    assert final["job_id"] == "append-final"
    assert final["status"] == "success"
    assert final["confirmations"] == []
    assert final["service_requests"] == []
    final_batch = StandardSummaryReader().read(final_output / "moisture_summary.xlsx").batches[0]
    assert final_batch.statistics.mean != draft_batch.statistics.mean
    assert (
        final_batch.statistics.mean
        == StandardSummaryReader()
        .read(_base_summary(new_raw, tmp_path / "new-only-output"))
        .batches[0]
        .statistics.mean
    )


def original_mean(summary: Path):
    return StandardSummaryReader().read(summary).batches[0].statistics.mean


def test_append_invalid_conflict_answer_fails_without_overwriting_inputs(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old" / "same-batch.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    new_raw = workbook_factory(
        tmp_path / "new" / "same-batch.xlsx",
        moisture_values=(0.53,),
        mass_values=((100, 47, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    config = _append_config(tmp_path)
    draft_output = tmp_path / "draft"
    assert run_draft(_job((base, new_raw), draft_output, config)) == 0
    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    before = {path: sha256_file(path) for path in (base, new_raw)}
    confirmation = tmp_path / "bad-confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "append-root",
                "answers": [
                    {
                        "confirmation_id": draft["confirmations"][0]["confirmation_id"],
                        "value": "overwrite_history",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "bad-final"

    assert (
        run_finalize(
            _job(
                (base, new_raw),
                final_output,
                config,
                phase=JobPhase.FINALIZE,
                confirmation_file=confirmation,
            )
        )
        == 0
    )

    result = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["errors"] == ["CONFIRMATION_ANSWER_INVALID"]
    assert result["outputs"] == []
    assert {path: sha256_file(path) for path in (base, new_raw)} == before


def test_default_year_and_history_conflict_replay_together(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old" / "same-batch.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    new_raw = workbook_factory(
        tmp_path / "new" / "same-batch.xlsx",
        moisture_values=(0.52,),
        mass_values=((100, 48, 0),),
        arrival_date="4月8日",
        test_date="4月9日",
    )
    config = _append_config(tmp_path)
    draft_output = tmp_path / "draft"
    assert run_draft(_job((base, new_raw), draft_output, config)) == 0
    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    prompts = {prompt["field"]: prompt for prompt in draft["confirmations"]}
    assert set(prompts) == {"default_year", "history_record_conflict"}

    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "append-root",
                "answers": [
                    {
                        "confirmation_id": prompts["default_year"]["confirmation_id"],
                        "value": 2026,
                        "apply_to_batch": True,
                    },
                    {
                        "confirmation_id": prompts["history_record_conflict"]["confirmation_id"],
                        "value": "use_new",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "final"

    assert (
        run_finalize(
            _job(
                (base, new_raw),
                final_output,
                config,
                phase=JobPhase.FINALIZE,
                confirmation_file=confirmation,
            )
        )
        == 0
    )

    result = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    assert result["confirmations"] == []
    batch = StandardSummaryReader().read(final_output / "moisture_summary.xlsx").batches[0]
    assert batch.record.test_date.isoformat() == "2026-04-09"
    assert batch.statistics.mean == Decimal("0.52")


def test_existing_formula_confirmation_applies_only_to_new_batch(
    tmp_path: Path,
    workbook_factory,
) -> None:
    old_raw = workbook_factory(
        tmp_path / "old-batch.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-08",
        test_date="2026-04-09",
    )
    base = _base_summary(old_raw, tmp_path / "base-output")
    historical_mean = original_mean(base)
    new_raw = workbook_factory(
        tmp_path / "new-batch.xlsx",
        moisture_values=(0.10,),
        mass_values=((100, 50, 0),),
        arrival_date="2026-04-10",
        test_date="2026-04-11",
    )
    config = _append_config(tmp_path)
    draft_output = tmp_path / "draft"
    assert run_draft(_job((base, new_raw), draft_output, config)) == 0
    draft = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    assert [prompt["field"] for prompt in draft["confirmations"]] == ["sample_1"]
    prompt = draft["confirmations"][0]

    confirmation = tmp_path / "confirmation.json"
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "append-root",
                "answers": [
                    {
                        "confirmation_id": prompt["confirmation_id"],
                        "value": "0.5",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "final"
    assert (
        run_finalize(
            _job(
                (base, new_raw),
                final_output,
                config,
                phase=JobPhase.FINALIZE,
                confirmation_file=confirmation,
            )
        )
        == 0
    )

    result = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success"
    batches = StandardSummaryReader().read(final_output / "moisture_summary.xlsx").batches
    assert batches[0].statistics.mean == historical_mean
    assert batches[1].statistics.mean == Decimal("0.5")
