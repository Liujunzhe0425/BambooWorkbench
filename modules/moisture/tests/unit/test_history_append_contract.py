from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.history_append_contract import (
    HistoryAppendConflict,
    HistoryConflictChoice,
    batch_business_fingerprint,
    build_history_conflict_prompt,
    history_conflict_confirmation_id,
    provisional_batch_key,
)
from moisture.domain.enums import ConfirmationState, DisplayColor, ReviewStatus, ScreenStatus
from moisture.domain.models import (
    AIReviewDecision,
    BatchRecord,
    BatchStatistics,
    SampleMeasurement,
    ScreeningDecision,
)
from moisture.ports.history_summary import HistoricalSummarySnapshot, SummaryFormat
from moisture.ports.writers import WorkbookBatch


def _batch(*, source_file: Path, source_hash: str, rule_hash: str = "b" * 64) -> WorkbookBatch:
    value = Decimal("0.51")
    sample = SampleMeasurement(
        sample_index=1,
        department_raw="品质",
        department="品质",
        source_row=5,
        initial_mass=Decimal("100"),
        dry_mass=Decimal("52"),
        foil_mass=Decimal("4"),
        source_moisture_value=value,
        verified_moisture_value=value,
        value_used_for_statistics=value,
    )
    record = BatchRecord(
        record_id="batch-stable-001",
        samples=(sample,),
        source_file=source_file,
        source_file_hash=source_hash,
        source_sheet="检测数据",
        supplier="供应商甲",
        material_type="原竹丝",
        arrival_date=date(2026, 4, 8),
        test_date=date(2026, 4, 9),
        total_weight_kg=Decimal("1200"),
    )
    statistics = BatchStatistics(
        sample_count=1,
        mean=value,
        total_average=value,
        standard_deviation=None,
        minimum=value,
        maximum=value,
        range_value=Decimal("0"),
        median=value,
        first_quartile=value,
        third_quartile=value,
        interquartile_range=Decimal("0"),
        department_averages={"品质": value},
        maximum_department_average_difference=Decimal("0"),
    )
    return WorkbookBatch(
        record=record,
        statistics=statistics,
        screening_decision=ScreeningDecision(status=ScreenStatus.NORMAL),
        ai_review=AIReviewDecision(status=ReviewStatus.NOT_COMPLETED),
        final_display_color=DisplayColor.NONE,
        confirmation_state=ConfirmationState.NOT_REQUIRED,
        rule_version="rules-v1",
        review_suggestion="按现行流程复核",
        rule_hash=rule_hash,
    )


def test_business_fingerprint_excludes_paths_source_hash_and_rule_state(
    tmp_path: Path,
) -> None:
    first = _batch(
        source_file=tmp_path / "one" / "source.xlsx",
        source_hash="a" * 64,
    )
    moved = _batch(
        source_file=tmp_path / "moved" / "renamed.xlsx",
        source_hash="c" * 64,
        rule_hash="d" * 64,
    )

    assert provisional_batch_key(first) == "batch-stable-001"
    assert batch_business_fingerprint(first) == batch_business_fingerprint(moved)

    changed_sample = replace(
        first.record.samples[0],
        value_used_for_statistics=Decimal("0.52"),
    )
    changed_record = replace(first.record, samples=(changed_sample,))
    assert batch_business_fingerprint(first) != batch_business_fingerprint(
        replace(first, record=changed_record)
    )


def test_conflict_confirmation_is_stable_and_has_only_two_frozen_choices() -> None:
    conflict = HistoryAppendConflict(
        record_id="batch-stable-001",
        existing_fingerprint="a" * 64,
        new_fingerprint="b" * 64,
        existing_display_name="history.xlsx",
        new_display_name="new.xlsx",
    )
    renamed = replace(
        conflict,
        existing_display_name="moved-history.xlsx",
        new_display_name="renamed-new.xlsx",
    )

    first = history_conflict_confirmation_id("draft-root", conflict)
    assert first == history_conflict_confirmation_id("draft-root", renamed)
    assert first != history_conflict_confirmation_id("other-root", conflict)

    prompt = build_history_conflict_prompt("draft-root", conflict)
    assert prompt["confirmation_id"] == first
    assert prompt["options"] == [
        HistoryConflictChoice.KEEP_EXISTING.value,
        HistoryConflictChoice.USE_NEW.value,
    ]
    assert prompt["suggested_value"] == HistoryConflictChoice.KEEP_EXISTING.value
    assert prompt["blocking"] is True
    assert "责任" not in str(prompt)
    assert "不合格" not in str(prompt)


def test_historical_snapshot_accepts_only_safe_unique_standard_batches(
    tmp_path: Path,
) -> None:
    batch = _batch(source_file=tmp_path / "source.xlsx", source_hash="a" * 64)
    snapshot = HistoricalSummarySnapshot(
        format_version=SummaryFormat.V1_0_1_FOUR_SHEET,
        source_sha256="f" * 64,
        source_display_name="summary.xlsx",
        batches=(batch,),
    )
    assert snapshot.batches == (batch,)

    with pytest.raises(ValueError, match="duplicate"):
        replace(snapshot, batches=(batch, batch))
    with pytest.raises(ValueError, match="safe file name"):
        replace(snapshot, source_display_name="C:\\customer\\summary.xlsx")
    with pytest.raises(ValueError, match="SHA-256"):
        replace(snapshot, source_sha256="not-a-hash")
