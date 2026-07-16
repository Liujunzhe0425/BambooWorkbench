from __future__ import annotations

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.deterministic_pipeline import DeterministicPipeline  # noqa: E402
from moisture.application.draft_orchestrator import run_draft  # noqa: E402
from moisture.contract.job_models import JobRequest  # noqa: E402

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_batch_preserves_order_and_isolates_duplicate_temporary_and_corrupt(
    tmp_path: Path, workbook_factory
) -> None:
    valid = workbook_factory(tmp_path / "valid.xlsx", moisture_values=(0.50,))
    duplicate = tmp_path / "duplicate.xlsx"
    duplicate.write_bytes(valid.read_bytes())
    temporary = tmp_path / "~$editing.xlsx"
    temporary.write_bytes(b"office-lock")
    corrupt = tmp_path / "corrupt.xlsx"
    corrupt.write_bytes(b"not-an-xlsx")

    outcome = DeterministicPipeline().run((valid, duplicate, temporary, corrupt))

    assert (outcome.processed_count, outcome.skipped_count, outcome.failed_count) == (1, 2, 1)
    assert [item["source_file"] for item in outcome.file_results] == [
        str(valid),
        str(duplicate),
        str(temporary),
        str(corrupt),
    ]
    assert outcome.file_results[1]["error"].startswith("DUPLICATE_CONTENT:")
    assert outcome.file_results[2]["error"].startswith("OFFICE_TEMPORARY_FILE:")
    assert outcome.file_results[3]["status"] == "failed"

    output_dir = tmp_path / "output"
    job = JobRequest.from_payload(
        {
            "schema_version": "1.0",
            "job_id": "job-t14-partial",
            "module_id": "moisture",
            "phase": "draft",
            "run_mode": "batch",
            "input_files": [str(path.resolve()) for path in (valid, duplicate, temporary, corrupt)],
            "output_dir": str(output_dir.resolve()),
        }
    )
    assert run_draft(job) == 0
    result = json.loads((output_dir / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "partial_success"
    assert result["summary"] == {
        "input_count": 4,
        "processed_count": 1,
        "skipped_count": 2,
        "failed_count": 1,
        "anomaly_count": 2,
        "confirmation_count": 0,
    }
    anomalies = result["anomalies"]
    assert [item["severity"] for item in anomalies] == ["info", "info"]
    assert [item["field"] for item in anomalies] == ["input_file", "input_file"]
    assert [item["source"]["source_file"] for item in anomalies] == [
        str(duplicate.resolve()),
        str(temporary.resolve()),
    ]
    assert [item["message"] for item in anomalies] == [
        "Duplicate workbook content skipped",
        "Office temporary workbook skipped",
    ]
    assert all(item["anomaly_id"].startswith("msr-anomaly-") for item in anomalies)
    assert all(str(tmp_path.resolve()) not in item["message"] for item in anomalies)

    second_output = tmp_path / "second-output"
    second_job = JobRequest.from_payload(
        {**job.to_payload(), "output_dir": str(second_output.resolve())}
    )
    assert run_draft(second_job) == 0
    second = json.loads((second_output / "result.json").read_text(encoding="utf-8"))
    assert [
        (item["anomaly_id"], item["field"], item["message"], item["source"])
        for item in second["anomalies"]
    ] == [
        (item["anomaly_id"], item["field"], item["message"], item["source"]) for item in anomalies
    ]


def test_all_invalid_files_are_a_legal_business_failure(tmp_path: Path) -> None:
    first = tmp_path / "bad-1.xlsx"
    second = tmp_path / "bad-2.xlsx"
    first.write_bytes(b"bad-one")
    second.write_bytes(b"bad-two")

    outcome = DeterministicPipeline().run((first, second))

    assert outcome.processed_count == 0
    assert outcome.failed_count == 2
    assert len(outcome.file_results) == 2
