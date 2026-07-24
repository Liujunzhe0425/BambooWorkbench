"""Deterministic orchestration for appending raw workbooks to a standard summary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from moisture.adapters.history.summary_reader import StandardSummaryReader
from moisture.application.confirmation_applier import (
    ConfirmationApplication,
    ConfirmationApplicationError,
    apply_confirmations,
)
from moisture.application.deterministic_pipeline import (
    DeterministicPipeline,
    DeterministicPipelineResult,
)
from moisture.application.history_append_contract import (
    HistoryAppendConflict,
    HistoryConflictChoice,
    batch_business_fingerprint,
    build_history_conflict_prompt,
    history_conflict_confirmation_id,
    provisional_batch_key,
)
from moisture.application.module_config import ModuleConfig
from moisture.application.run_result import InternalAnomaly
from moisture.contract.confirmation_reader import ConfirmationBundle
from moisture.contract.job_models import JobRequest
from moisture.domain.rules import PendingRuleMatch, RulePackageSnapshot
from moisture.infrastructure.file_integrity import FileIntegrityGuard
from moisture.ports.history_summary import HistoricalSummarySnapshot
from moisture.ports.writers import WorkbookBatch


class HistoryAppendError(ValueError):
    """A standard summary cannot be safely used as an append base."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HistoryConflictBinding:
    """Bind one user-visible conflict to immutable source identities."""

    binding_key: str
    conflict: HistoryAppendConflict


@dataclass(frozen=True, slots=True)
class HistoryAppendOutcome:
    """Outcome compatible with the normal artifact-writing boundary."""

    batches: tuple[WorkbookBatch, ...]
    new_outcome: DeterministicPipelineResult
    snapshot: HistoricalSummarySnapshot
    conflicts: tuple[HistoryConflictBinding, ...]
    file_results: tuple[dict[str, object], ...]
    input_count: int
    processed_count: int
    skipped_count: int
    failed_count: int
    rule_package: RulePackageSnapshot
    pending_rule_matches: tuple[PendingRuleMatch, ...] = ()
    anomalies: tuple[InternalAnomaly, ...] = ()
    errors: tuple[str, ...] = ()
    confirmation_issues: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class HistoryAppendApplication:
    batches: tuple[WorkbookBatch, ...]
    anomalies: tuple[InternalAnomaly, ...]


def _source_identity(batch: WorkbookBatch) -> str:
    value = batch.record.source_file_hash
    if isinstance(value, str) and value:
        return value
    return batch_business_fingerprint(batch)


def _binding_key(existing: WorkbookBatch, new: WorkbookBatch) -> str:
    payload = json.dumps(
        {
            "record_id": provisional_batch_key(new),
            "existing_source": _source_identity(existing),
            "new_source": _source_identity(new),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _display_name(batch: WorkbookBatch) -> str:
    source = batch.record.source_file
    return source.name if source is not None else f"{batch.record.record_id}.xlsx"


def _merge_batches(
    historical: tuple[WorkbookBatch, ...],
    new_batches: tuple[WorkbookBatch, ...],
    *,
    choices: Mapping[str, HistoryConflictChoice] | None = None,
    allowed_conflict_keys: set[str] | None = None,
) -> tuple[
    tuple[WorkbookBatch, ...],
    tuple[HistoryConflictBinding, ...],
    dict[str, str],
]:
    selected = {provisional_batch_key(batch): batch for batch in historical}
    seen_source_hashes = {
        batch.record.source_file_hash
        for batch in historical
        if isinstance(batch.record.source_file_hash, str) and batch.record.source_file_hash
    }
    conflicts: list[HistoryConflictBinding] = []
    skipped: dict[str, str] = {}

    for batch in new_batches:
        source_path = str(batch.record.source_file or "")
        source_hash = batch.record.source_file_hash
        if isinstance(source_hash, str) and source_hash and source_hash in seen_source_hashes:
            skipped[source_path] = "DUPLICATE_HISTORY_SOURCE"
            continue
        if isinstance(source_hash, str) and source_hash:
            seen_source_hashes.add(source_hash)

        record_id = provisional_batch_key(batch)
        existing = selected.get(record_id)
        if existing is None:
            selected[record_id] = batch
            continue

        existing_fingerprint = batch_business_fingerprint(existing)
        new_fingerprint = batch_business_fingerprint(batch)
        if existing_fingerprint == new_fingerprint:
            skipped[source_path] = "DUPLICATE_HISTORY_RECORD"
            continue

        binding = HistoryConflictBinding(
            binding_key=_binding_key(existing, batch),
            conflict=HistoryAppendConflict(
                record_id=record_id,
                existing_fingerprint=existing_fingerprint,
                new_fingerprint=new_fingerprint,
                existing_display_name=_display_name(existing),
                new_display_name=_display_name(batch),
            ),
        )
        if allowed_conflict_keys is not None and binding.binding_key not in allowed_conflict_keys:
            raise ConfirmationApplicationError(
                "a new history conflict appeared after applying confirmation answers"
            )
        conflicts.append(binding)
        choice = (choices or {}).get(
            binding.binding_key,
            HistoryConflictChoice.KEEP_EXISTING,
        )
        if choice is HistoryConflictChoice.USE_NEW:
            selected[record_id] = batch

    return tuple(selected.values()), tuple(conflicts), skipped


def _base_file_result(
    source: Path,
    snapshot: HistoricalSummarySnapshot,
) -> dict[str, object]:
    return {
        "source_file": str(source),
        "fingerprint": snapshot.source_sha256,
        "status": "success",
        "extracted_records": len(snapshot.batches),
        "missing_fields": [],
        "anomaly_count": 0,
        "error": None,
    }


def build_history_append_outcome(
    job: JobRequest,
    module_config: ModuleConfig,
    *,
    pipeline: DeterministicPipeline | None = None,
    default_year: int | None = None,
) -> HistoryAppendOutcome:
    """Read the base summary, process only new raw inputs, and merge a draft view."""

    base_index = module_config.base_summary_input_index
    raw_indexes = tuple(sorted(module_config.new_raw_input_indexes))
    if base_index is None or not raw_indexes:
        raise HistoryAppendError(
            "HISTORY_APPEND_CONFIG_INVALID",
            "append_summary input roles are incomplete",
        )

    base_source = job.input_files[base_index]
    try:
        checked = FileIntegrityGuard().read_checked(
            base_source,
            base_index,
            StandardSummaryReader().read,
        )
    except Exception as error:
        raise HistoryAppendError(
            "HISTORY_SUMMARY_INVALID",
            "the base summary is not a valid standard moisture workbook",
        ) from error
    snapshot = checked.value

    raw_sources = tuple(job.input_files[index] for index in raw_indexes)
    new_outcome = (pipeline or DeterministicPipeline()).run(
        raw_sources,
        default_year=(module_config.default_year if default_year is None else default_year),
    )
    merged, conflicts, history_skips = _merge_batches(
        snapshot.batches,
        new_outcome.batches,
    )

    result_by_index: dict[int, dict[str, object]] = {
        base_index: _base_file_result(base_source, snapshot)
    }
    for index, result in zip(raw_indexes, new_outcome.file_results, strict=True):
        adjusted = dict(result)
        skip_code = history_skips.get(str(job.input_files[index]))
        if skip_code is not None:
            adjusted["extracted_records"] = 0
            adjusted["anomaly_count"] = 0
            adjusted["error"] = f"{skip_code}: skipped"
        result_by_index[index] = adjusted

    history_skip_count = len(history_skips)
    return HistoryAppendOutcome(
        batches=merged,
        new_outcome=new_outcome,
        snapshot=snapshot,
        conflicts=conflicts,
        file_results=tuple(result_by_index[index] for index in range(len(job.input_files))),
        input_count=len(job.input_files),
        processed_count=1 + new_outcome.processed_count - history_skip_count,
        skipped_count=new_outcome.skipped_count + history_skip_count,
        failed_count=new_outcome.failed_count,
        rule_package=new_outcome.rule_package,
        pending_rule_matches=new_outcome.pending_rule_matches,
        anomalies=new_outcome.anomalies,
        errors=new_outcome.errors,
        confirmation_issues=new_outcome.confirmation_issues,
    )


def build_history_conflict_prompts(
    root_job_id: str,
    conflicts: tuple[HistoryConflictBinding, ...],
) -> tuple[dict[str, object], ...]:
    return tuple(
        sorted(
            (build_history_conflict_prompt(root_job_id, binding.conflict) for binding in conflicts),
            key=lambda prompt: str(prompt["confirmation_id"]),
        )
    )


def _history_choices(
    root_job_id: str,
    conflicts: tuple[HistoryConflictBinding, ...],
    bundle: ConfirmationBundle,
) -> dict[str, HistoryConflictChoice]:
    binding_by_confirmation_id = {
        history_conflict_confirmation_id(root_job_id, binding.conflict): binding
        for binding in conflicts
    }
    answers = {
        answer.confirmation_id: answer
        for answer in bundle.answers
        if answer.confirmation_id in binding_by_confirmation_id
    }
    if set(answers) != set(binding_by_confirmation_id):
        raise ConfirmationApplicationError("history conflict answer is incomplete")

    choices: dict[str, HistoryConflictChoice] = {}
    for confirmation_id, binding in binding_by_confirmation_id.items():
        answer = answers[confirmation_id]
        if answer.apply_to_batch or answer.remember_mapping:
            raise ConfirmationApplicationError(
                "history conflict answer does not allow batch or remembered application"
            )
        if not isinstance(answer.value, str):
            raise ConfirmationApplicationError("history conflict answer must be a string")
        try:
            choice = HistoryConflictChoice(answer.value)
        except ValueError as error:
            raise ConfirmationApplicationError(
                "history conflict answer is not an offered candidate"
            ) from error
        choices[binding.binding_key] = choice
    return choices


def apply_history_append_confirmations(
    outcome: HistoryAppendOutcome,
    *,
    root_job_id: str,
    original_conflicts: tuple[HistoryConflictBinding, ...],
    standard_prompts: tuple[Mapping[str, object], ...],
    bundle: ConfirmationBundle,
) -> HistoryAppendApplication:
    """Apply new-input answers, then merge them without recalculating history."""

    history_ids = {
        history_conflict_confirmation_id(root_job_id, binding.conflict)
        for binding in original_conflicts
    }
    standard_bundle = ConfirmationBundle(
        schema_version=bundle.schema_version,
        job_id=bundle.job_id,
        answers=tuple(
            answer for answer in bundle.answers if answer.confirmation_id not in history_ids
        ),
    )
    if standard_prompts:
        applied: ConfirmationApplication = apply_confirmations(
            outcome.new_outcome,
            standard_prompts,
            standard_bundle,
        )
        new_batches = applied.batches
        anomalies = applied.anomalies
    elif standard_bundle.answers:
        raise ConfirmationApplicationError("unexpected confirmation answer")
    else:
        new_batches = outcome.new_outcome.batches
        anomalies = outcome.new_outcome.anomalies

    choices = _history_choices(root_job_id, original_conflicts, bundle)
    allowed_keys = {binding.binding_key for binding in original_conflicts}
    batches, _, _ = _merge_batches(
        outcome.snapshot.batches,
        new_batches,
        choices=choices,
        allowed_conflict_keys=allowed_keys,
    )
    return HistoryAppendApplication(batches=batches, anomalies=anomalies)
