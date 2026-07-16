"""Stateless finalize orchestration over a fresh deterministic rerun."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from moisture.application.confirmation_applier import (
    ConfirmationApplicationError,
    apply_confirmations,
)
from moisture.application.confirmation_builder import build_confirmations
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import (
    _ai_request,
    _confirmation_issues,
    _global_failure_file_results,
    _load_default_year,
    _status,
)
from moisture.application.run_result import InternalMoistureRunResult, InternalOutput
from moisture.contract.confirmation_reader import read_confirmation_bundle
from moisture.contract.job_models import JobRequest
from moisture.contract.mapper import map_run_result
from moisture.infrastructure.atomic_write import AtomicResultWriter
from moisture.ports.writers import WorkbookReport
from moisture.reporting.markdown_writer import AnalysisReportView, write_analysis_markdown
from moisture.reporting.xlsx_writer import write_summary_xlsx


def _write_failed(job: JobRequest, started_at: datetime, code: str) -> int:
    internal = InternalMoistureRunResult(
        job_id=job.job_id,
        root_job_id=job.root_job_id,
        phase="finalize",
        input_count=len(job.input_files),
        processed_count=0,
        skipped_count=0,
        failed_count=len(job.input_files),
        file_results=_global_failure_file_results(job, code),
        analysis_summary="finalize 协议或确认答案无效，未形成正式业务结果",
        errors=(code,),
        business_failed=True,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    mapped = map_run_result(internal)
    AtomicResultWriter(job.output_dir).write(mapped.result)
    return mapped.exit_code


def run_finalize(job: JobRequest, pipeline: DeterministicPipeline | None = None) -> int:
    """Rebuild the draft from inputs and apply confirmation answers without hidden state."""

    started_at = datetime.now(UTC)
    try:
        default_year = _load_default_year(job.module_config_file)
        outcome = (pipeline or DeterministicPipeline()).run(
            job.input_files, default_year=default_year
        )
    except Exception:
        return _write_failed(job, started_at, "PIPELINE_INITIALIZATION_FAILED")

    prompts = build_confirmations(job.root_job_id, _confirmation_issues(outcome))
    expected_ids = {str(prompt["confirmation_id"]) for prompt in prompts}
    if prompts:
        read_result = read_confirmation_bundle(
            job.confirmation_file,
            root_job_id=job.root_job_id,
            expected_confirmation_ids=expected_ids,
            require_complete=False,
        )
        if read_result.errors or read_result.bundle is None:
            return _write_failed(job, started_at, "CONFIRMATION_PROTOCOL_INVALID")
        try:
            applied = apply_confirmations(outcome, prompts, read_result.bundle)
        except ConfirmationApplicationError:
            return _write_failed(job, started_at, "CONFIRMATION_ANSWER_INVALID")
        batches = applied.batches
        anomalies = applied.anomalies
    else:
        batches = outcome.batches
        anomalies = outcome.anomalies

    ai_request = _ai_request(job, outcome)
    errors = outcome.errors
    business_failed = outcome.processed_count == 0
    outputs: tuple[InternalOutput, ...] = ()
    if batches:
        completed_artifacts: list[Path] = []
        try:
            workbook_path = write_summary_xlsx(
                WorkbookReport(started_at=started_at, batches=batches), job.output_dir
            ).resolve()
            completed_artifacts.append(workbook_path)
            package = outcome.rule_package
            markdown_path = write_analysis_markdown(
                AnalysisReportView(
                    started_at=started_at,
                    status=_status(outcome.processed_count, outcome.failed_count),
                    batches=batches,
                    rule_version=package.rule_version,
                    rule_hash=package.rules_sha256,
                    rule_source=package.source,
                    rule_confirmation_status=package.customer_confirmation_status,
                    candidate_total=ai_request.candidate_total,
                    candidate_sent=ai_request.candidate_sent,
                    candidate_omitted=ai_request.candidate_omitted,
                    errors=errors,
                ),
                job.output_dir,
            ).resolve()
            completed_artifacts.append(markdown_path)
            outputs = (
                InternalOutput(
                    type="xlsx",
                    path=workbook_path,
                    label="竹丝含水率统计",
                    mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ),
                InternalOutput(
                    type="markdown",
                    path=markdown_path,
                    label="竹丝水分分析报告",
                    mime_type="text/markdown",
                ),
            )
        except Exception as error:
            for artifact in completed_artifacts:
                artifact.unlink(missing_ok=True)
            business_failed = True
            errors = (*errors, f"ARTIFACT_WRITE_FAILED: {type(error).__name__}")

    internal = InternalMoistureRunResult(
        job_id=job.job_id,
        root_job_id=job.root_job_id,
        phase="finalize",
        input_count=outcome.input_count,
        processed_count=outcome.processed_count,
        skipped_count=outcome.skipped_count,
        failed_count=outcome.failed_count,
        rule_version=outcome.rule_package.rule_version,
        anomalies=anomalies,
        outputs=outputs,
        file_results=outcome.file_results,
        confirmations=(),
        service_requests=(),
        analysis_summary="已重新运行确定性管线并应用有效人工确认",
        errors=errors,
        business_failed=business_failed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    mapped = map_run_result(internal)
    AtomicResultWriter(job.output_dir).write(mapped.result)
    return mapped.exit_code
