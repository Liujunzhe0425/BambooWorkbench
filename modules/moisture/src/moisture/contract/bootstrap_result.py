"""T03-only failed result used before moisture processing exists."""

from datetime import UTC, datetime
from typing import Any

from moisture import __version__

_NOT_IMPLEMENTED = (
    "MOISTURE_PROCESSING_NOT_IMPLEMENTED: "
    "the bootstrap contract does not process moisture input files"
)


def build_bootstrap_result(job: dict[str, Any], *, started_at: str) -> dict[str, Any]:
    input_files = job["input_files"]
    return {
        "schema_version": "1.0",
        "job_id": job["job_id"],
        "module_id": "moisture",
        "module_version": __version__,
        "status": "failed",
        "rule_version": None,
        "summary": {
            "input_count": len(input_files),
            "processed_count": 0,
            "skipped_count": 0,
            "failed_count": len(input_files),
            "anomaly_count": 0,
            "confirmation_count": 0,
        },
        "anomalies": [],
        "confirmations": [],
        "outputs": [],
        "file_results": [
            {
                "source_file": source_file,
                "fingerprint": "",
                "status": "failed",
                "extracted_records": 0,
                "missing_fields": [],
                "anomaly_count": 0,
                "error": _NOT_IMPLEMENTED,
            }
            for source_file in input_files
        ],
        "service_requests": [],
        "analysis_summary": (
            "Moisture processing is not implemented in the T03 bootstrap contract; "
            "no input data was processed and no business artifacts were produced."
        ),
        "errors": [_NOT_IMPLEMENTED],
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
    }
