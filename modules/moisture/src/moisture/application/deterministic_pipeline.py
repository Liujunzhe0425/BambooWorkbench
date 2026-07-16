"""Deterministic, offline batch orchestration for moisture workbooks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from moisture.adapters.excel.source_parser import ExcelSourceParser
from moisture.adapters.rules.builtin_evaluators import evaluate_rules
from moisture.adapters.rules.package_loader import RulePackageLoader
from moisture.application.run_result import InternalAnomaly, ReviewState
from moisture.domain.enums import (
    ConfirmationState,
    DisplayColor,
    ReviewStatus,
    ScreenStatus,
)
from moisture.domain.models import AIReviewDecision, ScreeningDecision
from moisture.domain.rules import PendingRuleMatch, RulePackageSnapshot
from moisture.domain.statistics import compute_batch_statistics
from moisture.infrastructure.file_integrity import FileIntegrityGuard
from moisture.infrastructure.hashing import sha256_file
from moisture.ports.writers import WorkbookBatch


@dataclass(frozen=True, slots=True)
class DeterministicPipelineResult:
    batches: tuple[WorkbookBatch, ...]
    file_results: tuple[dict[str, object], ...]
    input_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    rule_package: RulePackageSnapshot
    pending_rule_matches: tuple[PendingRuleMatch, ...] = ()
    anomalies: tuple[InternalAnomaly, ...] = ()
    errors: tuple[str, ...] = ()


def _module_root() -> Path:
    return Path(__file__).parents[3]


def _safe_failure(error: Exception) -> str:
    return f"WORKBOOK_PROCESSING_FAILED: {type(error).__name__}"


def _file_result(
    source: Path,
    fingerprint: str,
    status: str,
    *,
    extracted_records: int = 0,
    anomaly_count: int = 0,
    error: str | None = None,
) -> dict[str, object]:
    return {
        "source_file": str(source),
        "fingerprint": fingerprint,
        "status": status,
        "extracted_records": extracted_records,
        "missing_fields": [],
        "anomaly_count": anomaly_count,
        "error": error,
    }


class DeterministicPipeline:
    """Compose the migrated Task 1—9 business core without service access."""

    def __init__(self, module_root: Path | None = None) -> None:
        self.module_root = (module_root or _module_root()).resolve()
        self._parser = ExcelSourceParser()
        self._integrity = FileIntegrityGuard()

    def run(
        self, input_files: tuple[Path, ...], *, default_year: int | None = None
    ) -> DeterministicPipelineResult:
        snapshot = RulePackageLoader().load(self.module_root / "rules" / "active")
        batches: list[WorkbookBatch] = []
        file_results: list[dict[str, object]] = []
        pending_matches: list[PendingRuleMatch] = []
        anomalies: list[InternalAnomaly] = []
        errors: list[str] = []
        seen: dict[str, int] = {}
        processed = skipped = failed = 0

        for input_order, source in enumerate(input_files):
            if source.name.startswith("~$") and source.suffix.casefold() == ".xlsx":
                skipped += 1
                identity = hashlib.sha256(
                    f"office_temporary_file:{input_order}".encode()
                ).hexdigest()[:24]
                anomalies.append(
                    InternalAnomaly(
                        anomaly_id=f"msr-anomaly-{identity}",
                        review_state=ReviewState.SUSPECT_HIGH,
                        field="input_file",
                        message="Office temporary workbook skipped",
                        source_file=source,
                    )
                )
                file_results.append(
                    _file_result(
                        source,
                        "",
                        "success",
                        anomaly_count=1,
                        error="OFFICE_TEMPORARY_FILE: skipped",
                    )
                )
                continue
            try:
                fingerprint = sha256_file(source)
                canonical_order = seen.get(fingerprint)
                if canonical_order is not None:
                    skipped += 1
                    identity = hashlib.sha256(
                        f"duplicate_content:{fingerprint}:{canonical_order}".encode()
                    ).hexdigest()[:24]
                    anomalies.append(
                        InternalAnomaly(
                            anomaly_id=f"msr-anomaly-{identity}",
                            review_state=ReviewState.SUSPECT_HIGH,
                            field="input_file",
                            message="Duplicate workbook content skipped",
                            source_file=source,
                        )
                    )
                    file_results.append(
                        _file_result(
                            source,
                            fingerprint,
                            "success",
                            anomaly_count=1,
                            error=f"DUPLICATE_CONTENT: canonical input order {canonical_order}",
                        )
                    )
                    continue
                seen[fingerprint] = input_order
                checked = self._integrity.read_checked(
                    source,
                    input_order,
                    lambda path: self._parser.parse(path, default_year=default_year),
                )
                record = checked.value
                statistics = compute_batch_statistics(record)
                evaluation = evaluate_rules(record, snapshot)
                pending_matches.extend(evaluation.pending_matches)
                for decision in evaluation.decisions:
                    for hit in decision.rule_hits:
                        review_state = (
                            ReviewState.SUSPECT_HIGH
                            if hit.display_color is DisplayColor.ORANGE
                            else ReviewState.SUSPECT_LOW
                        )
                        identity = hashlib.sha256(
                            f"{fingerprint}:{hit.rule_id}:{hit.target_field}".encode()
                        ).hexdigest()[:24]
                        anomalies.append(
                            InternalAnomaly(
                                anomaly_id=f"msr-anomaly-{identity}",
                                review_state=review_state,
                                field=hit.target_field or "workbook",
                                message=hit.message,
                                source_file=source,
                                sheet=record.source_sheet,
                                rule_id=hit.rule_id,
                            )
                        )
                decision = (
                    evaluation.decisions[0]
                    if evaluation.decisions
                    else ScreeningDecision(status=ScreenStatus.NORMAL)
                )
                display_color = decision.display_color
                batch = WorkbookBatch(
                    record=record,
                    statistics=statistics,
                    screening_decision=decision,
                    ai_review=AIReviewDecision(
                        status=ReviewStatus.NOT_REQUIRED,
                        display_color=DisplayColor.NONE,
                        confirmation_state=ConfirmationState.NOT_REQUIRED,
                    ),
                    final_display_color=display_color,
                    confirmation_state=ConfirmationState.NOT_REQUIRED,
                    rule_version=snapshot.rule_version,
                    review_suggestion=(
                        "待业务确认规则未自动判定"
                        if evaluation.pending_matches
                        else "未发现已确认规则异常"
                    ),
                )
                batches.append(batch)
                processed += 1
                file_results.append(
                    _file_result(
                        source,
                        checked.identity.fingerprint,
                        "success",
                        extracted_records=1,
                        anomaly_count=len(evaluation.decisions),
                    )
                )
            except Exception as error:
                failed += 1
                message = _safe_failure(error)
                errors.append(f"{source.name}: {message}")
                file_results.append(
                    _file_result(
                        source,
                        fingerprint if "fingerprint" in locals() else "",
                        "failed",
                        error=message,
                    )
                )
            finally:
                if "fingerprint" in locals():
                    del fingerprint

        return DeterministicPipelineResult(
            batches=tuple(batches),
            file_results=tuple(file_results),
            input_count=len(input_files),
            processed_count=processed,
            skipped_count=skipped,
            failed_count=failed,
            rule_package=snapshot,
            pending_rule_matches=tuple(pending_matches),
            anomalies=tuple(anomalies),
            errors=tuple(errors),
        )
