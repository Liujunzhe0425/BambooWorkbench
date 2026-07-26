"""Build a private monthly snapshot from finalized deterministic batches."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from moisture.application.history_append_contract import batch_business_fingerprint
from moisture.contract.monthly_snapshot import (
    MonthlySnapshot,
    MonthlySnapshotError,
    MonthlySnapshotRecord,
)
from moisture.domain.models import RuleHit, ScreeningDecision
from moisture.ports.writers import WorkbookBatch


def _decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "0"
    return format(value.normalize(), "f")


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _rule_hit_payload(hit: RuleHit) -> dict[str, object]:
    return {
        "rule_id": hit.rule_id,
        "message": hit.message,
        "display_color": hit.display_color.value,
        "target_field": hit.target_field,
    }


def _decision_payload(decision: ScreeningDecision) -> dict[str, object]:
    return {
        "status": decision.status.value,
        "display_color": decision.display_color.value,
        "target_field": decision.target_field,
        "reason": decision.reason,
        "rule_hits": [_rule_hit_payload(hit) for hit in decision.rule_hits],
    }


def _record_payload(batch: WorkbookBatch) -> dict[str, object]:
    record = batch.record
    statistics = batch.statistics
    decisions = batch.screening_decisions or (
        () if batch.screening_decision.status.value == "normal" else (batch.screening_decision,)
    )
    return {
        "record_id": record.record_id,
        "business_fingerprint": batch_business_fingerprint(batch),
        "supplier": record.supplier,
        "material_type": record.material_type,
        "arrival_date": _date(record.arrival_date),
        "test_date": _date(record.test_date),
        "total_weight_kg": _decimal(record.total_weight_kg),
        "samples": [
            {
                "sample_index": sample.sample_index,
                "department": sample.department,
                "source_row": sample.source_row,
                "value": _decimal(sample.value_used_for_statistics),
            }
            for sample in sorted(record.samples, key=lambda item: item.sample_index)
        ],
        "statistics": {
            "sample_count": statistics.sample_count,
            "mean": _decimal(statistics.mean),
            "total_average": _decimal(statistics.total_average),
            "standard_deviation": _decimal(statistics.standard_deviation),
            "minimum": _decimal(statistics.minimum),
            "maximum": _decimal(statistics.maximum),
            "range_value": _decimal(statistics.range_value),
            "median": _decimal(statistics.median),
            "first_quartile": _decimal(statistics.first_quartile),
            "third_quartile": _decimal(statistics.third_quartile),
            "interquartile_range": _decimal(statistics.interquartile_range),
            "department_averages": [
                {"department": name, "value": _decimal(value)}
                for name, value in sorted(statistics.department_averages.items())
            ],
            "maximum_department_average_difference": _decimal(
                statistics.maximum_department_average_difference
            ),
        },
        "screening": {
            "primary": _decision_payload(batch.screening_decision),
            "decisions": [_decision_payload(decision) for decision in decisions],
            "final_display_color": batch.final_display_color.value,
            "confirmation_state": batch.confirmation_state.value,
            "review_suggestion": batch.review_suggestion,
            "lower_threshold": _decimal(batch.lower_threshold),
            "upper_threshold": _decimal(batch.upper_threshold),
        },
        "anomalies": [
            _decision_payload(decision)
            for decision in decisions
            if decision.display_color.value != "none"
        ],
        "traceability": {
            "source_display_name": f"{record.record_id}.xlsx",
            "source_file_hash": record.source_file_hash,
            "source_sheet": record.source_sheet,
            "rule_version": batch.rule_version,
            "rule_sha256": batch.rule_hash,
            "rule_applicable_scope": batch.rule_applicable_scope,
            "rule_confirmation_status": batch.rule_confirmation_status,
            "experience_references": [
                {
                "entry_id": reference.entry_id,
                "version": reference.version,
                "title": reference.title or reference.entry_id,
                "sha256": reference.content_hash or None,
                }
                for reference in sorted(
                    batch.experience_references,
                    key=lambda item: (item.entry_id, item.version),
                )
            ],
        },
    }


def _effective_date(batch: WorkbookBatch) -> date | None:
    return batch.record.test_date or batch.record.arrival_date


def _sort_key(batch: WorkbookBatch) -> tuple[date, str, str]:
    effective = _effective_date(batch)
    if effective is None:  # filtered before sorting
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_PERIOD_EMPTY",
            "monthly snapshot contains no records for the target period",
        )
    return (
        effective,
        batch.record.record_id,
        batch_business_fingerprint(batch),
    )


def build_monthly_snapshot(
    *,
    phase: str,
    module_version: str,
    year: int,
    month: int,
    rule_version: str,
    rule_sha256: str,
    batches: tuple[WorkbookBatch, ...],
) -> MonthlySnapshot:
    """Select this month's finalized records and build a deterministic snapshot."""

    if phase != "finalize":
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_NOT_FINAL",
            "monthly snapshot requires a finalized business result",
        )
    selected = tuple(
        batch
        for batch in batches
        if (effective := _effective_date(batch)) is not None
        and effective.year == year
        and effective.month == month
    )
    if not selected:
        raise MonthlySnapshotError(
            "MONTHLY_SNAPSHOT_PERIOD_EMPTY",
            "monthly snapshot contains no records for the target period",
        )
    for batch in selected:
        if batch.rule_version != rule_version or batch.rule_hash != rule_sha256:
            raise MonthlySnapshotError(
                "MONTHLY_SNAPSHOT_RULE_IDENTITY_INVALID",
                "monthly snapshot records do not match the task rule identity",
            )
    ordered = tuple(sorted(selected, key=_sort_key))
    return MonthlySnapshot(
        module_version=module_version,
        year=year,
        month=month,
        rule_version=rule_version,
        rule_sha256=rule_sha256,
        records=tuple(
            MonthlySnapshotRecord.from_payload(_record_payload(batch)) for batch in ordered
        ),
    )
