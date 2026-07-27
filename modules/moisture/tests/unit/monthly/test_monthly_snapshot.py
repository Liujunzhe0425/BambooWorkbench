from __future__ import annotations

# ruff: noqa: E402, I001

import json
import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.monthly_snapshot import build_monthly_snapshot
from moisture.contract.monthly_snapshot import (
    MonthlySnapshot,
    MonthlySnapshotError,
    canonical_snapshot_bytes,
    validate_monthly_snapshot_payload,
    write_monthly_snapshot,
)
from moisture.domain.enums import ConfirmationState, DisplayColor, ReviewStatus, ScreenStatus
from moisture.domain.models import (
    AIReviewDecision,
    BatchRecord,
    BatchStatistics,
    RuleHit,
    SampleMeasurement,
    ScreeningDecision,
)
from moisture.ports.writers import ExperienceCitation, WorkbookBatch

RULE_HASH = "b" * 64


def _batch(
    tmp_path: Path,
    *,
    record_id: str,
    test_date: date,
    value: str = "0.5100",
    rule_hash: str = RULE_HASH,
) -> WorkbookBatch:
    moisture = Decimal(value)
    sample = SampleMeasurement(
        sample_index=1,
        department_raw="品质",
        department="品质",
        source_row=5,
        initial_mass=Decimal("100"),
        dry_mass=Decimal("52"),
        foil_mass=Decimal("4"),
        source_moisture_value=moisture,
        verified_moisture_value=moisture,
        value_used_for_statistics=moisture,
    )
    record = BatchRecord(
        record_id=record_id,
        samples=(sample,),
        source_file=tmp_path / "private" / f"{record_id}.xlsx",
        source_file_hash=("a" if record_id == "batch-001" else "c") * 64,
        source_sheet="检测数据",
        supplier="供应商甲",
        material_type="原竹丝",
        arrival_date=test_date,
        test_date=test_date,
        total_weight_kg=Decimal("1200.00"),
    )
    statistics = BatchStatistics(
        sample_count=1,
        mean=moisture,
        total_average=moisture,
        standard_deviation=None,
        minimum=moisture,
        maximum=moisture,
        range_value=Decimal("0.0000"),
        median=moisture,
        first_quartile=moisture,
        third_quartile=moisture,
        interquartile_range=Decimal("0"),
        department_averages={"品质": moisture},
        maximum_department_average_difference=Decimal("0"),
    )
    decision = ScreeningDecision(
        status=ScreenStatus.HIGH,
        rule_hits=(
            RuleHit(
                rule_id="R-HIGH",
                message="偏高疑似",
                display_color=DisplayColor.ORANGE,
                target_field="mean",
            ),
        ),
        display_color=DisplayColor.ORANGE,
        reason="确定性筛查提示",
        target_field="mean",
    )
    return WorkbookBatch(
        record=record,
        statistics=statistics,
        screening_decision=decision,
        screening_decisions=(decision,),
        ai_review=AIReviewDecision(status=ReviewStatus.NOT_COMPLETED),
        final_display_color=DisplayColor.ORANGE,
        confirmation_state=ConfirmationState.CONFIRMED_ANOMALY,
        rule_version="rules-v2",
        review_suggestion="建议人工复核",
        rule_hash=rule_hash,
        rule_applicable_scope="原竹丝；全年",
        rule_confirmation_status="confirmed",
        lower_threshold=Decimal("0.47"),
        upper_threshold=Decimal("0.55"),
        experience_references=(
            ExperienceCitation(
                entry_id="EXP-001",
                version="1.0.0",
                title="复核指导",
                source="internal",
                content_hash="e" * 64,
            ),
        ),
    )


def _snapshot(tmp_path: Path) -> MonthlySnapshot:
    return build_monthly_snapshot(
        phase="finalize",
        module_version="1.3.1",
        year=2026,
        month=3,
        rule_version="rules-v2",
        rule_sha256=RULE_HASH,
        batches=(
            _batch(tmp_path, record_id="batch-002", test_date=date(2026, 3, 20)),
            _batch(tmp_path, record_id="batch-001", test_date=date(2026, 3, 8)),
            _batch(tmp_path, record_id="prior-001", test_date=date(2026, 1, 8)),
        ),
    )


def test_builder_keeps_only_target_month_and_serializes_deterministically(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(tmp_path)
    payload = snapshot.to_payload()

    assert [record["record_id"] for record in payload["records"]] == [
        "batch-001",
        "batch-002",
    ]
    assert payload["records"][0]["samples"][0]["value"] == "0.51"
    assert payload["records"][0]["statistics"]["range_value"] == "0"
    assert payload["records"][0]["traceability"]["source_display_name"] == "batch-001.xlsx"
    assert (
        payload["records"][0]["traceability"]["experience_references"][0]["sha256"]
        == "e" * 64
    )
    assert str(tmp_path) not in json.dumps(payload, ensure_ascii=False)
    validate_monthly_snapshot_payload(payload)

    rebuilt = MonthlySnapshot.from_payload(payload)
    assert canonical_snapshot_bytes(rebuilt) == canonical_snapshot_bytes(snapshot)


def test_builder_accepts_stable_unicode_business_record_ids(tmp_path: Path) -> None:
    snapshot = build_monthly_snapshot(
        phase="finalize",
        module_version="1.3.1",
        year=2026,
        month=4,
        rule_version="rules-v2",
        rule_sha256=RULE_HASH,
        batches=(
            _batch(
                tmp_path,
                record_id="002-4.10供应商甲原竹丝水分检测（2）",
                test_date=date(2026, 4, 10),
            ),
            _batch(
                tmp_path,
                record_id="001-4.10 供应商甲 原竹丝水分检测",
                test_date=date(2026, 4, 9),
            ),
        ),
    )

    payload = snapshot.to_payload()
    assert [record["record_id"] for record in payload["records"]] == [
        "001-4.10 供应商甲 原竹丝水分检测",
        "002-4.10供应商甲原竹丝水分检测（2）",
    ]
    assert payload["records"][1]["traceability"]["source_display_name"] == (
        "002-4.10供应商甲原竹丝水分检测（2）.xlsx"
    )
    assert MonthlySnapshot.from_payload(payload).to_payload() == payload


@pytest.mark.parametrize(
    "record_id",
    (
        "../客户批次",
        r"C:\客户\批次",
        "客户/批次",
        "客户\x00批次",
        "客户\x1f批次",
        " 客户批次",
        "客户批次 ",
    ),
)
def test_snapshot_rejects_path_like_or_control_character_record_ids(
    tmp_path: Path,
    record_id: str,
) -> None:
    payload = _snapshot(tmp_path).to_payload()
    payload["records"][0]["record_id"] = record_id

    with pytest.raises(MonthlySnapshotError) as error:
        MonthlySnapshot.from_payload(payload)

    assert error.value.code == "MONTHLY_SNAPSHOT_INVALID"
    assert str(tmp_path) not in str(error.value)
    assert record_id not in str(error.value)


def test_snapshot_rejects_duplicate_but_accepts_similar_record_ids(
    tmp_path: Path,
) -> None:
    payload = _snapshot(tmp_path).to_payload()
    duplicate = json.loads(json.dumps(payload))
    duplicate["records"][1]["record_id"] = duplicate["records"][0]["record_id"]
    with pytest.raises(MonthlySnapshotError) as duplicate_error:
        MonthlySnapshot.from_payload(duplicate)
    assert duplicate_error.value.code == "MONTHLY_SNAPSHOT_INVALID"

    similar = json.loads(json.dumps(payload))
    similar["records"][0]["record_id"] = "供应商甲原竹丝水分检测（1）"
    similar["records"][1]["record_id"] = "供应商甲原竹丝水分检测（2）"
    assert MonthlySnapshot.from_payload(similar).to_payload() == similar


def test_builder_requires_finalize_target_records_and_matching_rule_identity(
    tmp_path: Path,
) -> None:
    batch = _batch(tmp_path, record_id="batch-001", test_date=date(2026, 3, 8))
    arguments = {
        "module_version": "1.3.1",
        "year": 2026,
        "month": 3,
        "rule_version": "rules-v2",
        "rule_sha256": RULE_HASH,
        "batches": (batch,),
    }

    with pytest.raises(MonthlySnapshotError) as draft_error:
        build_monthly_snapshot(phase="draft", **arguments)
    assert draft_error.value.code == "MONTHLY_SNAPSHOT_NOT_FINAL"

    with pytest.raises(MonthlySnapshotError) as empty_error:
        build_monthly_snapshot(phase="finalize", **(arguments | {"month": 4}))
    assert empty_error.value.code == "MONTHLY_SNAPSHOT_PERIOD_EMPTY"

    mismatched = replace(batch, rule_hash="d" * 64)
    with pytest.raises(MonthlySnapshotError) as rule_error:
        build_monthly_snapshot(
            phase="finalize",
            **(arguments | {"batches": (mismatched,)}),
        )
    assert rule_error.value.code == "MONTHLY_SNAPSHOT_RULE_IDENTITY_INVALID"


def test_schema_rejects_unknown_fields_float_decimals_and_absolute_source(
    tmp_path: Path,
) -> None:
    payload = _snapshot(tmp_path).to_payload()

    invalid_extra = dict(payload)
    invalid_extra["unexpected"] = True
    with pytest.raises(MonthlySnapshotError) as extra_error:
        validate_monthly_snapshot_payload(invalid_extra)
    assert extra_error.value.code == "MONTHLY_SNAPSHOT_INVALID"

    invalid_float = json.loads(json.dumps(payload))
    invalid_float["records"][0]["statistics"]["mean"] = 0.51
    with pytest.raises(MonthlySnapshotError):
        validate_monthly_snapshot_payload(invalid_float)

    invalid_source = json.loads(json.dumps(payload))
    invalid_source["records"][0]["traceability"]["source_display_name"] = (
        "C:\\customer\\source.xlsx"
    )
    with pytest.raises(MonthlySnapshotError):
        validate_monthly_snapshot_payload(invalid_source)


def test_snapshot_semantics_reject_cross_month_and_unstable_record_order(
    tmp_path: Path,
) -> None:
    payload = _snapshot(tmp_path).to_payload()
    cross_month = json.loads(json.dumps(payload))
    cross_month["records"][0]["test_date"] = "2026-02-28"
    cross_month["records"][0]["arrival_date"] = "2026-02-28"
    with pytest.raises(MonthlySnapshotError) as period_error:
        MonthlySnapshot.from_payload(cross_month)
    assert period_error.value.code == "MONTHLY_SNAPSHOT_INVALID"

    unordered = json.loads(json.dumps(payload))
    unordered["records"].reverse()
    with pytest.raises(MonthlySnapshotError) as order_error:
        MonthlySnapshot.from_payload(unordered)
    assert order_error.value.code == "MONTHLY_SNAPSHOT_INVALID"


def test_record_payload_is_returned_as_a_fresh_copy(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    first = snapshot.records[0].to_payload()
    first["supplier"] = "已修改"

    assert snapshot.records[0].to_payload()["supplier"] == "供应商甲"


def test_atomic_write_matches_canonical_bytes_and_failure_preserves_old_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(tmp_path)
    output_dir = (tmp_path / "output").resolve()
    destination = write_monthly_snapshot(snapshot, output_dir)

    assert destination.read_bytes() == canonical_snapshot_bytes(snapshot)
    old_bytes = destination.read_bytes()

    from moisture.contract import monthly_snapshot

    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(monthly_snapshot.os, "replace", fail_replace)
    with pytest.raises(MonthlySnapshotError) as write_error:
        write_monthly_snapshot(snapshot, output_dir)
    assert write_error.value.code == "MONTHLY_SNAPSHOT_WRITE_FAILED"
    assert destination.read_bytes() == old_bytes
    assert not list(output_dir.glob(".moisture-monthly-snapshot.*.tmp"))


def test_atomic_writer_rejects_relative_output(tmp_path: Path) -> None:
    with pytest.raises(MonthlySnapshotError) as error:
        write_monthly_snapshot(_snapshot(tmp_path), Path("relative-output"))
    assert error.value.code == "MONTHLY_SNAPSHOT_WRITE_FAILED"
