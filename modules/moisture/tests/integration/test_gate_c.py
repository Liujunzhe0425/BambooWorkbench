# ruff: noqa: E402, I001

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from openpyxl import load_workbook

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.cli import main

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _write_job(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path.resolve()


def test_gate_c_cli_draft_to_offline_finalize_has_no_hidden_state(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "inputs" / "source.xlsx",
        departments={"品质": 1},
        moisture_values=(0.60,),
    )
    workbook = load_workbook(source)
    workbook.active["B5"] = 100
    workbook.active["C5"] = 40
    workbook.active["D5"] = 0
    workbook.active["E5"] = 0.61
    workbook.save(source)
    workbook.close()

    draft_dir = (tmp_path / "draft-output").resolve()
    draft_job = _write_job(
        tmp_path / "jobs" / "draft.json",
        {
            "schema_version": "1.0",
            "job_id": "gate-c-draft",
            "module_id": "moisture",
            "phase": "draft",
            "run_mode": "single",
            "input_files": [str(source.resolve())],
            "output_dir": str(draft_dir),
            "allowed_knowledge_scopes": ["moisture"],
        },
    )
    assert main(["run", "--job", str(draft_job)]) == 0
    draft = json.loads((draft_dir / "result.json").read_text(encoding="utf-8"))
    assert draft["confirmations"]
    assert not any(item["service"] == "ai" for item in draft["service_requests"])

    confirmation = tmp_path / "protocol" / "confirmation.json"
    confirmation.parent.mkdir(parents=True)
    confirmation.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "job_id": "gate-c-draft",
                "answers": [
                    {
                        "confirmation_id": item["confirmation_id"],
                        "value": item["options"][0],
                        "apply_to_batch": False,
                        "remember_mapping": False,
                    }
                    for item in draft["confirmations"]
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    service_file = tmp_path / "protocol" / "service-response.json"
    service_file.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task_id": "gate-c-draft",
                "module_id": "moisture",
                "responses": [
                    {
                        "request_id": item["request_id"],
                        "service": item["service"],
                        "status": "error",
                        "error": "offline",
                    }
                    for item in draft["service_requests"]
                ],
            }
        ),
        encoding="utf-8",
    )
    shutil.rmtree(draft_dir)

    final_dir = (tmp_path / "final-output").resolve()
    finalize_job = _write_job(
        tmp_path / "jobs" / "finalize.json",
        {
            "schema_version": "1.0",
            "job_id": "gate-c-finalize",
            "module_id": "moisture",
            "phase": "finalize",
            "run_mode": "single",
            "input_files": [str(source.resolve())],
            "output_dir": str(final_dir),
            "allowed_knowledge_scopes": ["moisture"],
            "parent_job_id": "gate-c-draft",
            "confirmation_file": str(confirmation.resolve()),
            "service_response_file": str(service_file.resolve()),
        },
    )
    assert main(["run", "--job", str(finalize_job)]) == 0
    result = json.loads((final_dir / "result.json").read_text(encoding="utf-8"))

    assert result["job_id"] == "gate-c-finalize"
    assert result["status"] == "success"
    assert result["confirmations"] == [] and result["service_requests"] == []
    assert (final_dir / "moisture_summary.xlsx").is_file()
    assert (final_dir / "analysis_report.md").is_file()
