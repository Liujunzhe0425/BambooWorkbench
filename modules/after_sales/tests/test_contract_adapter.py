from __future__ import annotations

import json
import sys
from pathlib import Path

import openpyxl


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent.cli import _create_sample_workbook, run_job  # noqa: E402
from core.contracts.result import ModuleResult  # noqa: E402


def _job(input_file: Path, output_dir: Path, **overrides):
    payload = {
        "schema_version": "1.0",
        "job_id": "adapter-draft",
        "module_id": "after_sales",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file)],
        "output_dir": str(output_dir),
        "module_config_file": None,
        "ai_enabled": False,
        "allowed_knowledge_scopes": [],
        "parent_job_id": None,
        "confirmation_file": None,
        "service_response_file": None,
    }
    payload.update(overrides)
    return payload


def test_draft_and_finalize_write_manual_fee_to_final_excel(tmp_path):
    input_file = tmp_path / "人工复核费用.xlsx"
    _create_sample_workbook(
        input_file,
        customer="示例客户",
        brand_text="桃花江竹地板",
        date_text="2026-05-10",
        feedback="竹地板开裂。",
        solution="已完成更换，费用待人工确认。",
    )

    draft_output = tmp_path / "draft"
    draft_job = _job(input_file, draft_output)
    draft_job_path = tmp_path / "draft-job.json"
    draft_job_path.write_text(json.dumps(draft_job, ensure_ascii=False), encoding="utf-8")
    assert run_job(draft_job_path) == 0

    draft_result = json.loads((draft_output / "result.json").read_text(encoding="utf-8"))
    ModuleResult.model_validate(draft_result)
    answers = []
    for prompt in draft_result["confirmations"]:
        value = 3200 if prompt["field"] == "fee_amount" else prompt.get("suggested_value")
        answers.append(
            {
                "confirmation_id": prompt["confirmation_id"],
                "value": value,
                "apply_to_batch": False,
                "remember_mapping": False,
            }
        )
    assert any(item["value"] == 3200 for item in answers)

    confirmation_file = tmp_path / "confirmation.json"
    confirmation_file.write_text(
        json.dumps(
            {"schema_version": "1.0", "job_id": "adapter-draft", "answers": answers},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    final_output = tmp_path / "final"
    final_job = _job(
        input_file,
        final_output,
        job_id="adapter-final",
        phase="finalize",
        parent_job_id="adapter-draft",
        confirmation_file=str(confirmation_file),
    )
    final_job_path = tmp_path / "final-job.json"
    final_job_path.write_text(json.dumps(final_job, ensure_ascii=False), encoding="utf-8")
    assert run_job(final_job_path) == 0

    final_result = json.loads((final_output / "result.json").read_text(encoding="utf-8"))
    ModuleResult.model_validate(final_result)
    assert final_result["status"] == "success"
    records = json.loads((final_output / "after_sales_records.json").read_text(encoding="utf-8"))
    assert records[0]["fee_amount"] == 3200
    assert records[0]["fee_status"] == "exact"

    workbook = openpyxl.load_workbook(final_output / "after_sales_summary.xlsx", data_only=True)
    assert any(
        cell.value == 3200
        for worksheet in workbook.worksheets
        for row in worksheet.iter_rows()
        for cell in row
    )
