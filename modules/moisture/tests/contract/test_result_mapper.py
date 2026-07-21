# ruff: noqa: E402, I001

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.run_result import (
    InternalAnomaly,
    InternalMoistureRunResult,
    InternalOutput,
    ReviewState,
)
from moisture.contract.mapper import ResultMappingError, map_run_result


STARTED = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)


def run_result(**overrides: object) -> InternalMoistureRunResult:
    values: dict[str, object] = {
        "job_id": "current-job",
        "phase": "draft",
        "input_count": 1,
        "processed_count": 1,
        "skipped_count": 0,
        "failed_count": 0,
        "started_at": STARTED,
        "finished_at": STARTED + timedelta(seconds=1),
    }
    values.update(overrides)
    return InternalMoistureRunResult(**values)


def test_mapper_uses_current_finalize_job_id() -> None:
    mapped = map_run_result(
        run_result(job_id="finalize-job", phase="finalize", root_job_id="draft-job")
    )

    assert mapped.result.job_id == "finalize-job"
    assert mapped.exit_code == 0


def test_valid_failed_result_maps_to_exit_zero() -> None:
    mapped = map_run_result(
        run_result(
            processed_count=0,
            failed_count=1,
            errors=("WORKBOOK_INVALID: workbook cannot be processed",),
        )
    )

    assert mapped.result.status.value == "failed"
    assert mapped.exit_code == 0


@pytest.mark.parametrize(
    ("state", "severity"),
    [
        (ReviewState.SUSPECT_HIGH, "info"),
        (ReviewState.SUSPECT_LOW, "info"),
        (ReviewState.HIGH_SUSPICION_HIGH, "warning"),
        (ReviewState.HIGH_SUSPICION_LOW, "warning"),
    ],
)
def test_mapper_owns_review_state_severity(
    state: ReviewState, severity: str
) -> None:
    anomaly = InternalAnomaly(
        anomaly_id="a-1",
        review_state=state,
        field="moisture",
        message="candidate",
        source_file=Path("C:/input/source.xlsx"),
    )

    mapped = map_run_result(run_result(anomalies=(anomaly,)))

    assert mapped.result.anomalies[0].severity.value == severity
    assert mapped.result.anomalies[0].severity.value != "critical"


def test_status_priority_is_failed_then_draft_confirmation_then_partial() -> None:
    confirmation = {
        "confirmation_id": "c-1",
        "field": "year",
        "reason": "ambiguous",
        "confidence": 0.5,
        "blocking": True,
        "batch_applicable": False,
        "rememberable": False,
        "source": {"source_file": "C:/input/source.xlsx"},
    }
    failed = map_run_result(
        run_result(
            processed_count=0,
            failed_count=1,
            confirmations=(confirmation,),
            errors=("FAILED: no processable input",),
        )
    )
    pending = map_run_result(run_result(confirmations=(confirmation,)))
    partial = map_run_result(run_result(input_count=2, failed_count=1))

    assert failed.result.status.value == "failed"
    assert pending.result.status.value == "needs_confirmation"
    assert partial.result.status.value == "partial_success"


def test_summary_counts_and_outputs_are_mapped_once(tmp_path: Path) -> None:
    output = tmp_path / "analysis_report.md"
    output.write_text("done", encoding="utf-8")

    mapped = map_run_result(
        run_result(
            input_count=2,
            processed_count=1,
            skipped_count=1,
            outputs=(
                InternalOutput(
                    type="report",
                    path=output,
                    label="Analysis report",
                    mime_type="text/markdown",
                ),
            ),
        )
    )

    assert mapped.result.summary.to_payload() == {
        "input_count": 2,
        "processed_count": 1,
        "skipped_count": 1,
        "failed_count": 0,
        "anomaly_count": 0,
        "confirmation_count": 0,
    }
    assert mapped.result.outputs[0].path == output


@pytest.mark.parametrize(
    ("input_count", "skipped_count"),
    [(1, 1), (2, 1)],
)
def test_no_processed_business_result_is_failed(
    input_count: int, skipped_count: int
) -> None:
    mapped = map_run_result(
        run_result(
            input_count=input_count,
            processed_count=0,
            skipped_count=skipped_count,
        )
    )

    assert mapped.result.status.value == "failed"


@pytest.mark.parametrize("field", ["confirmations", "service_requests"])
def test_finalize_rejects_new_follow_up_work(field: str) -> None:
    confirmation = {
        "confirmation_id": "c-1",
        "field": "year",
        "reason": "ambiguous",
        "confidence": 0.5,
        "blocking": True,
        "batch_applicable": False,
        "rememberable": False,
        "source": {"source_file": "C:/input/source.xlsx"},
    }
    service_request = {
        "request_id": "r-1",
        "service": "knowledge",
        "purpose": "review candidate",
        "payload": {},
    }

    with pytest.raises(ResultMappingError, match=field):
        map_run_result(
            run_result(
                phase="finalize",
                **{
                    field: (
                        confirmation if field == "confirmations" else service_request,
                    )
                },
            )
        )
