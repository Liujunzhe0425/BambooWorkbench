"""Draft orchestration from deterministic outcomes to formal artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from moisture.application.ai_request_builder import (
    AIRequestBuildResult,
    build_ai_request,
    candidates_from_batches,
)
from moisture.application.confirmation_builder import build_confirmations
from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.run_result import InternalMoistureRunResult, InternalOutput
from moisture.application.service_request_builder import build_knowledge_request
from moisture.contract.job_models import JobRequest
from moisture.contract.mapper import map_run_result
from moisture.domain.models import BusinessConfirmationIssue
from moisture.infrastructure.atomic_write import AtomicResultWriter
from moisture.ports.writers import WorkbookReport
from moisture.reporting.markdown_writer import AnalysisReportView, write_analysis_markdown
from moisture.reporting.xlsx_writer import write_summary_xlsx


class ModuleConfigError(ValueError):
    """The optional, module-owned deterministic configuration is invalid."""


_FORMULA_CONFIRMATION_TOLERANCE = Decimal("0.0001")


def _reject_duplicate_config_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModuleConfigError("duplicate configuration key")
        result[key] = value
    return result


def _load_default_year(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_config_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModuleConfigError("configuration must be readable UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ModuleConfigError("configuration must be a JSON object")
    unknown = set(payload) - {"default_year"}
    if unknown:
        raise ModuleConfigError("configuration contains unknown fields")
    default_year = payload.get("default_year")
    if default_year is None:
        return None
    if type(default_year) is not int or not 1900 <= default_year <= 2100:
        raise ModuleConfigError("default_year must be an integer from 1900 to 2100")
    return default_year


def _status(processed: int, failed: int) -> str:
    if processed == 0:
        return "failed"
    return "partial_success" if failed else "success"


def _global_failure_file_results(job: JobRequest, message: str) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "source_file": str(source),
            "fingerprint": "",
            "status": "failed",
            "extracted_records": 0,
            "missing_fields": [],
            "anomaly_count": 0,
            "error": message,
        }
        for source in job.input_files
    )


def _confirmation_issues(outcome: object) -> tuple[BusinessConfirmationIssue, ...]:
    issues = list(getattr(outcome, "confirmation_issues", ()))
    batches = tuple(getattr(outcome, "batches", ()))
    if batches:
        record = batches[0].record
        if record.source_file_hash and record.source_file is not None:
            for match in getattr(outcome, "pending_rule_matches", ()):
                issues.append(
                    BusinessConfirmationIssue(
                        kind="rule_scope",
                        fingerprint=record.source_file_hash,
                        field=match.target_field or "rule_scope",
                        candidates=("适用", "不适用"),
                        source_file=record.source_file,
                        sheet=record.source_sheet,
                        rule_hash=match.rules_sha256,
                    )
                )
    for batch in batches:
        record = batch.record
        fingerprint = record.source_file_hash
        source_file = record.source_file
        if not fingerprint or source_file is None:
            continue
        for sample in record.samples:
            source_value = sample.source_moisture_value
            verified_value = sample.verified_moisture_value
            if (
                source_value is None
                or verified_value is None
                or abs(source_value - verified_value) <= _FORMULA_CONFIRMATION_TOLERANCE
            ):
                continue
            issues.append(
                BusinessConfirmationIssue(
                    kind="formula_conflict",
                    fingerprint=fingerprint,
                    field=f"sample_{sample.sample_index}",
                    candidates=(str(source_value), str(verified_value)),
                    suggested_value=str(source_value),
                    source_file=source_file,
                    sheet=record.source_sheet,
                    cell_or_range=f"row:{sample.source_row}",
                )
            )
    return tuple(issues)


def _knowledge_requests(job: JobRequest, outcome: object) -> tuple[dict[str, object], ...]:
    pending = tuple(getattr(outcome, "pending_rule_matches", ()))
    needed = bool(pending) or bool(getattr(outcome, "knowledge_guidance_needed", False))
    rule_hash = outcome.rule_package.rules_sha256
    digest_source = (
        "|".join(sorted(f"{item.rule_id}:{item.target_field or ''}" for item in pending))
        or "general-guidance"
    )
    candidate_digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    request = build_knowledge_request(
        root_job_id=job.root_job_id,
        allowed_scopes=job.allowed_knowledge_scopes,
        needed=needed,
        rule_hash=rule_hash,
        candidate_digest=candidate_digest,
    )
    return (request,) if request is not None else ()


def _ai_request(job: JobRequest, outcome: object) -> AIRequestBuildResult:
    candidates = tuple(getattr(outcome, "ai_review_candidates", ()))
    if not candidates:
        candidates = candidates_from_batches(tuple(outcome.batches), outcome.rule_package)
    return build_ai_request(
        root_job_id=job.root_job_id,
        candidates=candidates,
        rule_hash=outcome.rule_package.rules_sha256,
    )


def run_draft(job: JobRequest, pipeline: DeterministicPipeline | None = None) -> int:
    """Run one draft and publish ``result.json`` after completed artifacts."""

    started_at = datetime.now(UTC)
    try:
        default_year = _load_default_year(job.module_config_file)
        outcome = (pipeline or DeterministicPipeline()).run(
            job.input_files, default_year=default_year
        )
    except ModuleConfigError:
        message = "MODULE_CONFIG_INVALID"
        internal = InternalMoistureRunResult(
            job_id=job.job_id,
            root_job_id=job.root_job_id,
            phase="draft",
            input_count=len(job.input_files),
            processed_count=0,
            skipped_count=0,
            failed_count=len(job.input_files),
            file_results=_global_failure_file_results(job, message),
            analysis_summary="模块配置无效，未处理输入工作簿。",
            errors=(message,),
            business_failed=True,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        mapped = map_run_result(internal)
        AtomicResultWriter(job.output_dir).write(mapped.result)
        return mapped.exit_code
    except Exception as error:
        message = f"PIPELINE_INITIALIZATION_FAILED: {type(error).__name__}"
        internal = InternalMoistureRunResult(
            job_id=job.job_id,
            root_job_id=job.root_job_id,
            phase="draft",
            input_count=len(job.input_files),
            processed_count=0,
            skipped_count=0,
            failed_count=len(job.input_files),
            file_results=_global_failure_file_results(job, message),
            analysis_summary="确定性管线初始化失败。",
            errors=(message,),
            business_failed=True,
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )
        mapped = map_run_result(internal)
        AtomicResultWriter(job.output_dir).write(mapped.result)
        return mapped.exit_code
    outputs: tuple[InternalOutput, ...] = ()
    errors = outcome.errors
    business_failed = outcome.processed_count == 0
    knowledge_requests = _knowledge_requests(job, outcome)
    ai_request = _ai_request(job, outcome)
    service_requests = knowledge_requests + ((ai_request.request,) if ai_request.request else ())

    if outcome.batches:
        completed_artifacts: list[Path] = []
        try:
            workbook_path = write_summary_xlsx(
                WorkbookReport(started_at=started_at, batches=outcome.batches),
                job.output_dir,
            ).resolve()
            completed_artifacts.append(workbook_path)
            package = outcome.rule_package
            markdown_path = write_analysis_markdown(
                AnalysisReportView(
                    started_at=started_at,
                    status=_status(outcome.processed_count, outcome.failed_count),
                    batches=outcome.batches,
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
            outputs = ()
            business_failed = True
            errors = (*errors, f"ARTIFACT_WRITE_FAILED: {type(error).__name__}")

    internal = InternalMoistureRunResult(
        job_id=job.job_id,
        root_job_id=job.root_job_id,
        phase="draft",
        input_count=outcome.input_count,
        processed_count=outcome.processed_count,
        skipped_count=outcome.skipped_count,
        failed_count=outcome.failed_count,
        rule_version=outcome.rule_package.rule_version,
        anomalies=outcome.anomalies,
        outputs=outputs,
        file_results=outcome.file_results,
        confirmations=build_confirmations(job.root_job_id, _confirmation_issues(outcome)),
        service_requests=service_requests,
        analysis_summary=(
            f"已处理 {outcome.processed_count} 个工作簿，"
            f"跳过 {outcome.skipped_count} 个，失败 {outcome.failed_count} 个。"
        ),
        errors=errors,
        business_failed=business_failed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    mapped = map_run_result(internal)
    AtomicResultWriter(job.output_dir).write(mapped.result)
    return mapped.exit_code
