"""Draft orchestration from deterministic outcomes to formal artifacts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from moisture.application.deterministic_pipeline import DeterministicPipeline
from moisture.application.run_result import InternalMoistureRunResult, InternalOutput
from moisture.contract.job_models import JobRequest
from moisture.contract.mapper import map_run_result
from moisture.infrastructure.atomic_write import AtomicResultWriter
from moisture.ports.writers import WorkbookReport
from moisture.reporting.markdown_writer import AnalysisReportView, write_analysis_markdown
from moisture.reporting.xlsx_writer import write_summary_xlsx


class ModuleConfigError(ValueError):
    """The optional, module-owned deterministic configuration is invalid."""


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
                    candidate_total=0,
                    candidate_sent=0,
                    candidate_omitted=0,
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
        confirmations=(),
        service_requests=(),
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
