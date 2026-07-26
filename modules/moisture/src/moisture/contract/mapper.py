"""The single mapping boundary from internal moisture outcomes to ModuleResult."""

from __future__ import annotations

from dataclasses import dataclass

from moisture import __version__
from moisture.application.run_result import (
    InternalAnomaly,
    InternalMoistureRunResult,
    ReviewState,
)
from moisture.contract.job_models import ModuleId
from moisture.contract.result_models import (
    Anomaly,
    ConfirmationPrompt,
    FileResult,
    ModuleResult,
    MonthlySnapshotArtifact,
    OutputArtifact,
    ResultSummary,
    ServiceRequest,
    Severity,
    SourceRef,
    TaskStatus,
)


class ResultMappingError(ValueError):
    """Internal data cannot be represented by the framework contract."""


@dataclass(frozen=True, slots=True)
class MappedRunResult:
    result: ModuleResult
    exit_code: int


_SEVERITY_BY_REVIEW_STATE = {
    ReviewState.SUSPECT_HIGH: Severity.INFO,
    ReviewState.SUSPECT_LOW: Severity.INFO,
    ReviewState.HIGH_SUSPICION_HIGH: Severity.WARNING,
    ReviewState.HIGH_SUSPICION_LOW: Severity.WARNING,
}


def _status(run: InternalMoistureRunResult) -> TaskStatus:
    no_business_result = run.processed_count == 0 and not run.cancelled
    if run.business_failed or no_business_result:
        return TaskStatus.FAILED
    if run.cancelled:
        return TaskStatus.CANCELLED
    if run.phase == "draft" and run.confirmations:
        return TaskStatus.NEEDS_CONFIRMATION
    if run.failed_count:
        return TaskStatus.PARTIAL_SUCCESS
    return TaskStatus.SUCCESS


def _anomaly(item: InternalAnomaly) -> Anomaly:
    return Anomaly.from_payload(
        {
            "anomaly_id": item.anomaly_id,
            "severity": _SEVERITY_BY_REVIEW_STATE[item.review_state].value,
            "field": item.field,
            "value": item.value,
            "rule_id": item.rule_id,
            "message": item.message,
            "suggestion": item.suggestion,
            "source": SourceRef(
                source_file=item.source_file,
                sheet=item.sheet,
                cell_or_range=item.cell_or_range,
            ).to_payload(),
        }
    )


def _check_counts(run: InternalMoistureRunResult) -> None:
    counts = (
        run.input_count,
        run.processed_count,
        run.skipped_count,
        run.failed_count,
    )
    if any(count < 0 for count in counts):
        raise ResultMappingError("run counts cannot be negative")
    if run.processed_count + run.skipped_count + run.failed_count > run.input_count:
        raise ResultMappingError("run counts exceed the input count")
    if run.phase not in {"draft", "finalize"}:
        raise ResultMappingError("run phase must be draft or finalize")
    if run.phase == "finalize" and run.confirmations:
        raise ResultMappingError("finalize confirmations must be empty")
    if run.phase == "finalize" and run.service_requests:
        raise ResultMappingError("finalize service_requests must be empty")
    if any(
        timestamp.tzinfo is None or timestamp.utcoffset() is None
        for timestamp in (run.started_at, run.finished_at)
    ):
        raise ResultMappingError("run timestamps must include a UTC offset")
    if run.finished_at < run.started_at:
        raise ResultMappingError("finished_at precedes started_at")


def map_run_result(run: InternalMoistureRunResult) -> MappedRunResult:
    """Map a legal internal outcome; every business status exits successfully."""

    _check_counts(run)
    anomalies = tuple(_anomaly(item) for item in run.anomalies)
    confirmations = tuple(
        ConfirmationPrompt.from_payload(item) for item in run.confirmations
    )
    result = ModuleResult(
        schema_version="1.0",
        job_id=run.job_id,
        module_id=ModuleId.MOISTURE,
        module_version=__version__,
        status=_status(run),
        rule_version=run.rule_version,
        summary=ResultSummary(
            input_count=run.input_count,
            processed_count=run.processed_count,
            skipped_count=run.skipped_count,
            failed_count=run.failed_count,
            anomaly_count=len(anomalies),
            confirmation_count=len(confirmations),
        ),
        anomalies=anomalies,
        confirmations=confirmations,
        outputs=tuple(
            OutputArtifact(
                type=item.type,
                path=item.path,
                label=item.label,
                mime_type=item.mime_type,
            )
            for item in run.outputs
        ),
        monthly_snapshot=(
            MonthlySnapshotArtifact.from_payload(run.monthly_snapshot)
            if run.monthly_snapshot is not None
            else None
        ),
        file_results=tuple(FileResult.from_payload(item) for item in run.file_results),
        service_requests=tuple(
            ServiceRequest.from_payload(item) for item in run.service_requests
        ),
        analysis_summary=run.analysis_summary,
        errors=run.errors,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
    return MappedRunResult(result=result, exit_code=0)
