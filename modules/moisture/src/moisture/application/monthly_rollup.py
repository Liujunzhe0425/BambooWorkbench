"""Completely offline, stateless annual rollup rendering from monthly snapshots."""

from __future__ import annotations

import hashlib
import json
import stat
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from moisture.contract.monthly_rollup import (
    MonthlyRollupArtifact,
    MonthlyRollupError,
    MonthlyRollupRequest,
    MonthlyRollupResult,
    MonthlySnapshotReference,
)
from moisture.contract.monthly_snapshot import MonthlySnapshot, MonthlySnapshotError
from moisture.domain.enums import (
    ConfirmationState,
    DisplayColor,
    ReviewStatus,
    ScreenStatus,
)
from moisture.domain.models import (
    AIReviewDecision,
    BatchRecord,
    BatchStatistics,
    RuleHit,
    SampleMeasurement,
    ScreeningDecision,
)
from moisture.infrastructure.atomic_write import write_json_atomic
from moisture.infrastructure.hashing import sha256_file
from moisture.ports.writers import (
    ExperienceCitation,
    WorkbookBatch,
    WorkbookReport,
)
from moisture.reporting.markdown_writer import AnalysisReportView, write_analysis_markdown
from moisture.reporting.xlsx_writer import write_summary_xlsx

_MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024
_OUTPUTS = (
    "moisture_summary.xlsx",
    "analysis_report.md",
    "moisture_business_records.json",
)


def _is_reparse_point(path: Path) -> bool:
    try:
        linked = path.lstat()
    except OSError:
        return False
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(getattr(linked, "st_file_attributes", 0) & flag)


def _validated_roots(request: MonthlyRollupRequest) -> tuple[Path, Path]:
    snapshot_root = request.snapshot_root
    output_dir = request.output_dir
    if (
        not snapshot_root.is_dir()
        or _is_reparse_point(snapshot_root)
        or not output_dir.is_dir()
        or _is_reparse_point(output_dir)
    ):
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_OUTPUT_PATH_INVALID",
            "monthly rollup authorized directories are invalid",
        )
    try:
        resolved_snapshot_root = snapshot_root.resolve(strict=True)
        resolved_output_dir = output_dir.resolve(strict=True)
    except OSError as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_OUTPUT_PATH_INVALID",
            "monthly rollup authorized directories are invalid",
        ) from error
    if any((resolved_output_dir / name).exists() for name in _OUTPUTS):
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_OUTPUT_PATH_INVALID",
            "monthly rollup staging directory already contains formal artifacts",
        )
    return resolved_snapshot_root, resolved_output_dir


def _snapshot_bytes(reference: MonthlySnapshotReference, root: Path) -> bytes:
    candidate = reference.path
    if not candidate.is_file() or _is_reparse_point(candidate):
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
            "monthly rollup snapshot is unavailable",
        )
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root) or resolved.stat().st_size > _MAX_SNAPSHOT_BYTES:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
                "monthly rollup snapshot is outside the authorized input root",
            )
        content = resolved.read_bytes()
    except MonthlyRollupError:
        raise
    except OSError as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
            "monthly rollup snapshot could not be read",
        ) from error
    if hashlib.sha256(content).hexdigest() != reference.sha256:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_HASH_MISMATCH",
            "monthly rollup snapshot hash does not match",
        )
    return content


def _load_snapshots(
    request: MonthlyRollupRequest,
    root: Path,
) -> tuple[MonthlySnapshot, ...]:
    loaded: list[MonthlySnapshot] = []
    for reference in request.snapshots:
        try:
            payload = json.loads(_snapshot_bytes(reference, root).decode("utf-8"))
            snapshot = MonthlySnapshot.from_payload(payload)
        except MonthlyRollupError:
            raise
        except (UnicodeError, json.JSONDecodeError, MonthlySnapshotError) as error:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
                "monthly rollup snapshot payload is invalid",
            ) from error
        if snapshot.module_id != request.module_id:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_MODULE_MISMATCH",
                "monthly rollup snapshot belongs to a different module",
            )
        if snapshot.year != request.year:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_YEAR_MISMATCH",
                "monthly rollup snapshot belongs to a different year",
            )
        if snapshot.month != reference.month:
            raise MonthlyRollupError(
                "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
                "monthly rollup declared month does not match the snapshot",
            )
        loaded.append(snapshot)
    latest = loaded[-1]
    if (
        latest.rule_version != request.business_config_version
        or latest.rule_sha256 != request.business_config_sha256
    ):
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
            "monthly rollup business configuration does not match the latest snapshot",
        )
    return tuple(loaded)


def _decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _date(value: object) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


def _rule_hit(payload: Mapping[str, Any]) -> RuleHit:
    return RuleHit(
        rule_id=str(payload["rule_id"]),
        message=str(payload["message"]),
        display_color=DisplayColor(str(payload["display_color"])),
        target_field=payload["target_field"],
    )


def _decision(payload: Mapping[str, Any]) -> ScreeningDecision:
    hits = payload["rule_hits"]
    if not isinstance(hits, list):
        raise TypeError
    return ScreeningDecision(
        status=ScreenStatus(str(payload["status"])),
        rule_hits=tuple(_rule_hit(hit) for hit in hits if isinstance(hit, Mapping)),
        display_color=DisplayColor(str(payload["display_color"])),
        reason=None if payload["reason"] is None else str(payload["reason"]),
        target_field=payload["target_field"],
    )


def _batch(payload: Mapping[str, Any]) -> WorkbookBatch:
    samples_payload = payload["samples"]
    statistics_payload = payload["statistics"]
    screening_payload = payload["screening"]
    traceability = payload["traceability"]
    if (
        not isinstance(samples_payload, list)
        or not isinstance(statistics_payload, Mapping)
        or not isinstance(screening_payload, Mapping)
        or not isinstance(traceability, Mapping)
    ):
        raise TypeError
    samples = tuple(
        SampleMeasurement(
            sample_index=int(sample["sample_index"]),
            department_raw=str(sample["department"]),
            department=str(sample["department"]),
            source_row=int(sample["source_row"]),
            initial_mass=Decimal("0"),
            dry_mass=Decimal("0"),
            foil_mass=Decimal("0"),
            source_moisture_value=_decimal(sample["value"]),
            verified_moisture_value=_decimal(sample["value"]),
            value_used_for_statistics=_decimal(sample["value"]),
        )
        for sample in samples_payload
        if isinstance(sample, Mapping)
    )
    department_payload = statistics_payload["department_averages"]
    decisions_payload = screening_payload["decisions"]
    references_payload = traceability["experience_references"]
    if (
        not isinstance(department_payload, list)
        or not isinstance(decisions_payload, list)
        or not isinstance(references_payload, list)
    ):
        raise TypeError
    record = BatchRecord(
        record_id=str(payload["record_id"]),
        samples=samples,
        source_file=Path(str(traceability["source_display_name"])),
        source_file_hash=traceability["source_file_hash"],
        source_sheet=traceability["source_sheet"],
        supplier=payload["supplier"],
        material_type=payload["material_type"],
        arrival_date=_date(payload["arrival_date"]),
        test_date=_date(payload["test_date"]),
        total_weight_kg=_decimal(payload["total_weight_kg"]),
    )
    statistics = BatchStatistics(
        sample_count=int(statistics_payload["sample_count"]),
        mean=Decimal(str(statistics_payload["mean"])),
        total_average=Decimal(str(statistics_payload["total_average"])),
        standard_deviation=_decimal(statistics_payload["standard_deviation"]),
        minimum=Decimal(str(statistics_payload["minimum"])),
        maximum=Decimal(str(statistics_payload["maximum"])),
        range_value=Decimal(str(statistics_payload["range_value"])),
        median=_decimal(statistics_payload["median"]),
        first_quartile=_decimal(statistics_payload["first_quartile"]),
        third_quartile=_decimal(statistics_payload["third_quartile"]),
        interquartile_range=_decimal(statistics_payload["interquartile_range"]),
        department_averages={
            str(item["department"]): Decimal(str(item["value"]))
            for item in department_payload
            if isinstance(item, Mapping)
        },
        maximum_department_average_difference=_decimal(
            statistics_payload["maximum_department_average_difference"]
        ),
    )
    primary_payload = screening_payload["primary"]
    if not isinstance(primary_payload, Mapping):
        raise TypeError
    primary = _decision(primary_payload)
    decisions = tuple(
        _decision(decision)
        for decision in decisions_payload
        if isinstance(decision, Mapping)
    )
    return WorkbookBatch(
        record=record,
        statistics=statistics,
        screening_decision=primary,
        screening_decisions=decisions,
        ai_review=AIReviewDecision(status=ReviewStatus.NOT_COMPLETED),
        final_display_color=DisplayColor(str(screening_payload["final_display_color"])),
        confirmation_state=ConfirmationState(str(screening_payload["confirmation_state"])),
        rule_version=str(traceability["rule_version"]),
        rule_hash=str(traceability["rule_sha256"]),
        rule_applicable_scope=str(traceability["rule_applicable_scope"]),
        rule_confirmation_status=str(traceability["rule_confirmation_status"]),
        lower_threshold=_decimal(screening_payload["lower_threshold"]),
        upper_threshold=_decimal(screening_payload["upper_threshold"]),
        review_suggestion=str(screening_payload["review_suggestion"]),
        experience_references=tuple(
            ExperienceCitation(
                entry_id=str(reference["entry_id"]),
                version=str(reference["version"]),
                title=str(reference["title"]),
                source=(
                    f"monthly_snapshot:{reference['entry_id']}:{reference['version']}"
                ),
                content_hash=(
                    "" if reference["sha256"] is None else str(reference["sha256"])
                ),
            )
            for reference in references_payload
            if isinstance(reference, Mapping)
        ),
    )


def _ordered_batches(snapshots: tuple[MonthlySnapshot, ...]) -> tuple[WorkbookBatch, ...]:
    batches: list[WorkbookBatch] = []
    record_ids: set[str] = set()
    try:
        for snapshot in snapshots:
            for record in snapshot.records:
                payload = record.to_payload()
                record_id = str(payload["record_id"])
                if record_id in record_ids:
                    raise MonthlyRollupError(
                        "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
                        "monthly rollup contains a duplicate business record",
                    )
                record_ids.add(record_id)
                batches.append(_batch(payload))
    except MonthlyRollupError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
            "monthly rollup snapshot cannot be restored",
        ) from error

    maximum_date = date.max
    return tuple(
        sorted(
            batches,
            key=lambda batch: (
                batch.record.test_date or batch.record.arrival_date or maximum_date,
                batch.record.record_id,
                batch.record.source_file_hash or "",
            ),
        )
    )


def _business_records_payload(
    request: MonthlyRollupRequest,
    snapshots: tuple[MonthlySnapshot, ...],
) -> dict[str, object]:
    records = [
        record.to_payload()
        for snapshot in snapshots
        for record in snapshot.records
    ]
    records.sort(
        key=lambda record: (
            str(record["test_date"] or record["arrival_date"]),
            str(record["record_id"]),
            str(record["business_fingerprint"]),
        )
    )
    return {
        "schema_version": "1.0",
        "module_id": "moisture",
        "target_period": {"year": request.year, "month": request.month},
        "used_months": [snapshot.month for snapshot in snapshots],
        "snapshot_hashes": [
            {"month": reference.month, "sha256": reference.sha256}
            for reference in request.snapshots
        ],
        "record_count": len(records),
        "records": records,
    }


def _artifact(path: Path, *, type: str, label: str, mime_type: str) -> MonthlyRollupArtifact:
    return MonthlyRollupArtifact(
        path=path.name,
        type=type,
        label=label,
        mime_type=mime_type,
        sha256=sha256_file(path),
    )


def _validated_artifact(path: Path, output_dir: Path, expected_name: str) -> Path:
    if path.name != expected_name or not path.is_file() or _is_reparse_point(path):
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_ARTIFACT_WRITE_FAILED",
            "monthly rollup writer returned an invalid artifact",
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_ARTIFACT_WRITE_FAILED",
            "monthly rollup artifact could not be verified",
        ) from error
    if resolved.parent != output_dir:
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_ARTIFACT_WRITE_FAILED",
            "monthly rollup artifact escaped the authorized output directory",
        )
    return resolved


def render_monthly_rollup(request: MonthlyRollupRequest) -> MonthlyRollupResult:
    """Validate immutable snapshots and render one complete offline annual result."""

    snapshot_root, output_dir = _validated_roots(request)
    snapshots = _load_snapshots(request, snapshot_root)
    batches = _ordered_batches(snapshots)
    latest = snapshots[-1]
    latest_trace = latest.records[-1].to_payload()["traceability"]
    if not isinstance(latest_trace, Mapping):  # snapshot schema invariant
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_SNAPSHOT_INVALID",
            "monthly rollup latest traceability is invalid",
        )
    logical_started_at = datetime(request.year, request.month, 1, tzinfo=UTC)

    completed: list[Path] = []
    try:
        workbook = _validated_artifact(
            write_summary_xlsx(
                WorkbookReport(started_at=logical_started_at, batches=batches),
                output_dir,
            ),
            output_dir,
            "moisture_summary.xlsx",
        )
        completed.append(workbook)
        markdown = _validated_artifact(
            write_analysis_markdown(
                AnalysisReportView(
                    started_at=logical_started_at,
                    status="success",
                    batches=batches,
                    rule_version=latest.rule_version,
                    rule_hash=latest.rule_sha256,
                    rule_source=f"monthly_snapshot:{latest.month:02d}",
                    rule_applicable_scope=str(latest_trace["rule_applicable_scope"]),
                    rule_confirmation_status=str(
                        latest_trace["rule_confirmation_status"]
                    ),
                    candidate_total=0,
                    candidate_sent=0,
                    candidate_omitted=0,
                    input_count=len(batches),
                    processed_count=len(batches),
                ),
                output_dir,
            ),
            output_dir,
            "analysis_report.md",
        )
        completed.append(markdown)
        business_records = output_dir / "moisture_business_records.json"
        write_json_atomic(
            business_records,
            _business_records_payload(request, snapshots),
        )
        business_records = _validated_artifact(
            business_records,
            output_dir,
            "moisture_business_records.json",
        )
        completed.append(business_records)
    except Exception as error:
        for name in _OUTPUTS:
            (output_dir / name).unlink(missing_ok=True)
        if isinstance(error, MonthlyRollupError):
            raise
        raise MonthlyRollupError(
            "MONTHLY_ROLLUP_ARTIFACT_WRITE_FAILED",
            "monthly rollup artifacts could not be written",
        ) from error

    artifacts = (
        _artifact(
            completed[0],
            type="xlsx",
            label="竹丝含水率累计统计",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        _artifact(
            completed[1],
            type="markdown",
            label="竹丝水分累计分析报告",
            mime_type="text/markdown",
        ),
        _artifact(
            completed[2],
            type="json",
            label="竹丝水分累计业务记录",
            mime_type="application/json",
        ),
    )
    return MonthlyRollupResult(
        year=request.year,
        month=request.month,
        used_months=tuple(snapshot.month for snapshot in snapshots),
        snapshot_hashes=tuple(
            (reference.month, reference.sha256) for reference in request.snapshots
        ),
        record_count=len(batches),
        artifacts=artifacts,
    )
