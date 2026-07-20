"""T03 bootstrap outcome routed through the shared T05 result mapper."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moisture.application.run_result import InternalMoistureRunResult
from moisture.contract.mapper import map_run_result

_NOT_IMPLEMENTED = (
    "MOISTURE_PROCESSING_NOT_IMPLEMENTED: "
    "the bootstrap contract does not process moisture input files"
)


def build_bootstrap_result(job: dict[str, Any], *, started_at: str) -> dict[str, Any]:
    input_files = job["input_files"]
    outcome = InternalMoistureRunResult(
        job_id=job["job_id"],
        root_job_id=job.get("parent_job_id") or job["job_id"],
        phase=job["phase"],
        input_count=len(input_files),
        processed_count=0,
        skipped_count=0,
        failed_count=len(input_files),
        started_at=datetime.fromisoformat(started_at),
        finished_at=datetime.now(UTC),
        file_results=tuple(
            {
                "source_file": str(Path(source_file)),
                "fingerprint": "",
                "status": "failed",
                "extracted_records": 0,
                "missing_fields": [],
                "anomaly_count": 0,
                "error": _NOT_IMPLEMENTED,
            }
            for source_file in input_files
        ),
        analysis_summary=(
            "Moisture processing is not implemented in the T03 bootstrap contract; "
            "no input data was processed and no business artifacts were produced."
        ),
        errors=(_NOT_IMPLEMENTED,),
        business_failed=True,
    )
    return map_run_result(outcome).result.to_payload()
