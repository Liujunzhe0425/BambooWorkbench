"""Deterministic, offline batch orchestration for moisture workbooks."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

from moisture.adapters.excel.source_parser import (
    ExcelSourceParser,
    record_requires_default_year,
)
from moisture.adapters.experience.local_approved_repository import (
    ExperienceRepositoryError,
    LocalApprovedExperienceRepository,
)
from moisture.adapters.rules.builtin_evaluators import evaluate_rules
from moisture.adapters.rules.package_loader import RulePackageLoader
from moisture.application.decision_aggregation import ordered_decisions, primary_decision
from moisture.application.run_result import InternalAnomaly, ReviewState
from moisture.application.screening_presentation import (
    screening_bounds,
    screening_suggestion,
)
from moisture.domain.enums import (
    ConfirmationState,
    DisplayColor,
    ReviewStatus,
)
from moisture.domain.models import (
    AIReviewDecision,
    BusinessConfirmationIssue,
)
from moisture.domain.rules import PendingRuleMatch, RulePackageSnapshot
from moisture.domain.statistics import compute_batch_statistics
from moisture.infrastructure.file_integrity import FileIntegrityGuard
from moisture.infrastructure.hashing import sha256_file
from moisture.ports.experience_repository import ExperienceQuery, ExperienceRepository
from moisture.ports.writers import ExperienceCitation, WorkbookBatch
from moisture.runtime_paths import module_root as runtime_module_root


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
    confirmation_issues: tuple[BusinessConfirmationIssue, ...] = ()


def _module_root() -> Path:
    return runtime_module_root()


def _safe_failure(error: Exception) -> str:
    code = getattr(error, "code", "WORKBOOK_PROCESSING_FAILED")
    if not isinstance(code, str) or not code:
        code = "WORKBOOK_PROCESSING_FAILED"
    return f"{code}: {type(error).__name__}"


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

    def __init__(
        self,
        module_root: Path | None = None,
        experience_repository: ExperienceRepository | None = None,
    ) -> None:
        self.module_root = (module_root or _module_root()).resolve()
        self._parser = ExcelSourceParser()
        self._integrity = FileIntegrityGuard()
        self._experience_repository = experience_repository
        experience_root = self.module_root / "experience"
        if self._experience_repository is None and experience_root.is_dir():
            try:
                self._experience_repository = LocalApprovedExperienceRepository(experience_root)
            except ExperienceRepositoryError:
                self._experience_repository = None

    def _experience_citations(
        self,
        record,
    ) -> tuple[tuple[ExperienceCitation, ...], str | None]:
        if self._experience_repository is None:
            return (), None
        observed = record.arrival_date or record.test_date
        if observed is None:
            return (), None
        as_of = datetime.combine(
            observed,
            time.max,
            tzinfo=timezone(timedelta(hours=8)),
        )
        try:
            references = self._experience_repository.search(
                ExperienceQuery.from_record(
                    record,
                    "total_average",
                    as_of=as_of,
                )
            )
        except (ExperienceRepositoryError, OSError, ValueError):
            return (), "EXPERIENCE_GUIDANCE_DEGRADED"
        return (
            tuple(
                ExperienceCitation(
                    entry_id=reference.experience_id,
                    version=reference.version,
                    title=reference.title,
                    source=reference.source,
                )
                for reference in references[:10]
            ),
            None,
        )

    def run(
        self, input_files: tuple[Path, ...], *, default_year: int | None = None
    ) -> DeterministicPipelineResult:
        snapshot = RulePackageLoader().load(self.module_root / "rules" / "active")
        batches: list[WorkbookBatch] = []
        file_results: list[dict[str, object]] = []
        pending_matches: list[PendingRuleMatch] = []
        anomalies: list[InternalAnomaly] = []
        errors: list[str] = []
        confirmation_issues: list[BusinessConfirmationIssue] = []
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
                if default_year is None and record_requires_default_year(record):
                    confirmation_issues.append(
                        BusinessConfirmationIssue(
                            kind="default_year",
                            fingerprint=checked.identity.fingerprint,
                            field="default_year",
                            candidates=(),
                            source_file=source,
                            sheet=record.source_sheet,
                            cell_or_range="arrival_date/test_date",
                        )
                    )
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
                decisions = ordered_decisions(evaluation.decisions)
                decision = primary_decision(decisions)
                lower_threshold, upper_threshold = screening_bounds(evaluation)
                display_color = decision.display_color
                experience_references, experience_error = self._experience_citations(record)
                if experience_error is not None and experience_error not in errors:
                    errors.append(experience_error)
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
                    review_suggestion=screening_suggestion(
                        decision.status,
                        lower_threshold,
                        upper_threshold,
                        pending=bool(evaluation.pending_matches),
                        target_field=decision.target_field,
                    ),
                    rule_hash=snapshot.rules_sha256,
                    rule_applicable_scope=snapshot.applicable_scope,
                    rule_confirmation_status=snapshot.customer_confirmation_status,
                    lower_threshold=lower_threshold,
                    upper_threshold=upper_threshold,
                    experience_references=experience_references,
                    screening_decisions=decisions,
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

        frozen_batches = tuple(batches)
        return DeterministicPipelineResult(
            batches=frozen_batches,
            file_results=tuple(file_results),
            input_count=len(input_files),
            processed_count=processed,
            skipped_count=skipped,
            failed_count=failed,
            rule_package=snapshot,
            pending_rule_matches=tuple(pending_matches),
            anomalies=tuple(anomalies),
            errors=tuple(errors),
            confirmation_issues=tuple(confirmation_issues),
        )
