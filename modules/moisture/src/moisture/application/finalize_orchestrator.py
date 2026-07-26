"""Stateless finalize orchestration over a fresh deterministic rerun."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from moisture import __version__
from moisture.application.confirmation_applier import (
    ConfirmationApplicationError,
    apply_confirmations,
    extract_default_year_answer,
)
from moisture.application.confirmation_builder import build_confirmations
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.draft_orchestrator import (
    _confirmation_issues,
    _confirmation_prompts,
    _global_failure_file_results,
    _knowledge_requests,
    _status,
)
from moisture.application.history_append import (
    HistoryAppendError,
    HistoryConflictBinding,
    apply_history_append_confirmations,
    build_history_append_outcome,
)
from moisture.application.knowledge_response import (
    KnowledgeResponseValidationError,
    validate_knowledge_citations,
)
from moisture.application.module_config import (
    ModuleConfigError,
    ModuleOperation,
    load_module_config,
)
from moisture.application.monthly_snapshot import build_monthly_snapshot
from moisture.application.run_result import InternalMoistureRunResult, InternalOutput
from moisture.contract.confirmation_reader import read_confirmation_bundle
from moisture.contract.job_models import JobRequest
from moisture.contract.mapper import map_run_result
from moisture.contract.monthly_snapshot import write_monthly_snapshot
from moisture.contract.service_response_reader import read_service_responses
from moisture.infrastructure.atomic_write import AtomicResultWriter
from moisture.ports.writers import KnowledgeCitation, WorkbookReport
from moisture.reporting.markdown_writer import (
    AnalysisReportView,
    write_analysis_markdown,
)
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
    append_mode = False
    original_history_conflicts: tuple[HistoryConflictBinding, ...] = ()
    try:
        module_config = load_module_config(job.module_config_file, input_count=len(job.input_files))
        if module_config.operation is ModuleOperation.AI_REPORT:
            from moisture.application.ai_report import run_ai_report_finalize

            return run_ai_report_finalize(job, module_config)
        selection = module_config.rule_selection
        active_pipeline = pipeline or DeterministicPipeline(
            rule_version=selection.version if selection else None,
            rules_sha256=selection.sha256 if selection else None,
        )
        if module_config.operation is ModuleOperation.APPEND_SUMMARY:
            append_mode = True
            outcome = build_history_append_outcome(
                job,
                module_config,
                pipeline=active_pipeline,
            )
            original_history_conflicts = outcome.conflicts
        else:
            outcome = active_pipeline.run(
                job.input_files, default_year=module_config.default_year
            )
    except ModuleConfigError:
        return _write_failed(job, started_at, "MODULE_CONFIG_INVALID")
    except Exception as error:
        if isinstance(error, HistoryAppendError):
            return _write_failed(job, started_at, error.code)
        return _write_failed(job, started_at, "PIPELINE_INITIALIZATION_FAILED")

    prompts = _confirmation_prompts(job, outcome)
    expected_ids = {str(prompt["confirmation_id"]) for prompt in prompts}
    if prompts:
        read_result = read_confirmation_bundle(
            job.confirmation_file,
            root_job_id=job.root_job_id,
            expected_confirmation_ids=expected_ids,
            require_complete=False,
            ignored_confirmation_id_prefixes=("service-consent:",),
        )
        if read_result.errors or read_result.bundle is None:
            return _write_failed(job, started_at, "CONFIRMATION_PROTOCOL_INVALID")
        try:
            confirmed_year, remaining_prompts, remaining_bundle = extract_default_year_answer(
                prompts, read_result.bundle
            )
            if confirmed_year is not None:
                if append_mode:
                    outcome = build_history_append_outcome(
                        job,
                        module_config,
                        pipeline=active_pipeline,
                        default_year=confirmed_year,
                    )
                else:
                    outcome = active_pipeline.run(
                        job.input_files, default_year=confirmed_year
                    )
                rebuilt_standard = build_confirmations(
                    job.root_job_id,
                    _confirmation_issues(getattr(outcome, "new_outcome", outcome)),
                    learning_enabled=job.learning_enabled,
                )
                previous_standard = tuple(
                    prompt
                    for prompt in remaining_prompts
                    if prompt.get("field") != "history_record_conflict"
                )
                if {str(prompt["confirmation_id"]) for prompt in rebuilt_standard} != {
                    str(prompt["confirmation_id"]) for prompt in previous_standard
                }:
                    raise ConfirmationApplicationError(
                        "confirmation set changed after resolving the default year"
                    )
                history_prompts = tuple(
                    prompt
                    for prompt in remaining_prompts
                    if prompt.get("field") == "history_record_conflict"
                )
                remaining_prompts = tuple(
                    sorted(
                        (*rebuilt_standard, *history_prompts),
                        key=lambda prompt: str(prompt["confirmation_id"]),
                    )
                )
            if remaining_prompts:
                if append_mode:
                    standard_prompts = tuple(
                        prompt
                        for prompt in remaining_prompts
                        if prompt.get("field") != "history_record_conflict"
                    )
                    applied = apply_history_append_confirmations(
                        outcome,
                        root_job_id=job.root_job_id,
                        original_conflicts=original_history_conflicts,
                        standard_prompts=standard_prompts,
                        bundle=remaining_bundle,
                    )
                else:
                    applied = apply_confirmations(
                        outcome,
                        remaining_prompts,
                        remaining_bundle,
                    )
                batches = applied.batches
                anomalies = applied.anomalies
            elif remaining_bundle.answers:
                raise ConfirmationApplicationError("unexpected confirmation answer")
            else:
                batches = outcome.batches
                anomalies = outcome.anomalies
        except ConfirmationApplicationError:
            return _write_failed(job, started_at, "CONFIRMATION_ANSWER_INVALID")
    else:
        batches = outcome.batches
        anomalies = outcome.anomalies

    knowledge_requests = _knowledge_requests(job, outcome)
    rebuilt_requests = knowledge_requests
    errors = outcome.errors
    knowledge_citations: tuple[KnowledgeCitation, ...] = ()
    business_failed = outcome.processed_count == 0
    if rebuilt_requests:
        expected_requests = {
            str(request["request_id"]): str(request["service"]) for request in rebuilt_requests
        }
        response_result = read_service_responses(
            job.service_response_file,
            root_job_id=job.root_job_id,
            expected_requests=expected_requests,
        )
        if response_result.errors or response_result.envelope is None:
            errors = (*errors, "SERVICE_RESPONSE_DEGRADED: invalid_or_missing")
        if response_result.envelope is not None:
            try:
                knowledge_citations = validate_knowledge_citations(
                    response_result.envelope.responses,
                    allowed_scopes=set(job.allowed_knowledge_scopes),
                )
            except KnowledgeResponseValidationError:
                errors = (*errors, "KNOWLEDGE_RESPONSE_DEGRADED")
    outputs: tuple[InternalOutput, ...] = ()
    monthly_snapshot: dict[str, object] | None = None
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
                    rule_applicable_scope=package.applicable_scope,
                    rule_confirmation_status=package.customer_confirmation_status,
                    candidate_total=0,
                    candidate_sent=0,
                    candidate_omitted=0,
                    input_count=outcome.input_count,
                    processed_count=outcome.processed_count,
                    skipped_count=outcome.skipped_count,
                    failed_count=outcome.failed_count,
                    knowledge_citations=knowledge_citations,
                    errors=errors,
                ),
                job.output_dir,
            ).resolve()
            completed_artifacts.append(markdown_path)
            if job.period_year is not None and job.period_month is not None:
                snapshot = build_monthly_snapshot(
                    phase="finalize",
                    module_version=__version__,
                    year=job.period_year,
                    month=job.period_month,
                    rule_version=outcome.rule_package.rule_version,
                    rule_sha256=outcome.rule_package.rules_sha256,
                    batches=tuple(batches),
                )
                snapshot_path = write_monthly_snapshot(
                    snapshot,
                    job.output_dir,
                ).resolve()
                completed_artifacts.append(snapshot_path)
                monthly_snapshot = {
                    "schema_version": "1.0",
                    "path": str(snapshot_path),
                    "snapshot_format": "moisture-v1",
                    "year": job.period_year,
                    "month": job.period_month,
                }
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
        monthly_snapshot=monthly_snapshot,
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
