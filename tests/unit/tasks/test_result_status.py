from datetime import UTC, datetime

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.result import FileResult, ModuleResult, ResultSummary
from core.tasks.result_status import effective_task_status, normalized_result


def _result(*, status: TaskStatus, failed_count: int, file_status: TaskStatus) -> ModuleResult:
    now = datetime.now(UTC)
    return ModuleResult(
        schema_version="1.0",
        job_id="status-policy-job",
        module_id=ModuleId.BOILING,
        module_version="1.0.0",
        status=status,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=failed_count,
            anomaly_count=7,
            confirmation_count=0,
        ),
        file_results=[
            FileResult(
                source_file="sample.xlsx",
                fingerprint="a" * 64,
                status=file_status,
                extracted_records=1,
                anomaly_count=7,
            )
        ],
        started_at=now,
        finished_at=now,
    )


def test_business_anomalies_do_not_make_task_partial() -> None:
    result = _result(
        status=TaskStatus.PARTIAL_SUCCESS,
        failed_count=0,
        file_status=TaskStatus.PARTIAL_SUCCESS,
    )

    assert effective_task_status(result) is TaskStatus.SUCCESS
    assert normalized_result(result).status is TaskStatus.SUCCESS
    assert result.status is TaskStatus.PARTIAL_SUCCESS


def test_actual_file_failure_remains_partial_when_other_work_succeeded() -> None:
    result = _result(
        status=TaskStatus.PARTIAL_SUCCESS,
        failed_count=1,
        file_status=TaskStatus.FAILED,
    )
    result = result.model_copy(
        update={
            "summary": result.summary.model_copy(
                update={"input_count": 2, "processed_count": 2}
            )
        }
    )

    assert effective_task_status(result) is TaskStatus.PARTIAL_SUCCESS
