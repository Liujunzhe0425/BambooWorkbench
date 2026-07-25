"""Integration tests for StandardSummaryReader — v1.0.0 and v1.0.1 formats."""

from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.history.summary_reader import StandardSummaryReader
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
    SampleMeasurement,
    ScreeningDecision,
)
from moisture.ports.history_summary import SummaryFormat
from moisture.ports.writers import ExperienceCitation, WorkbookBatch, WorkbookReport
from moisture.reporting.xlsx_writer import write_summary_xlsx


# ---------------------------------------------------------------------------
# Helpers to build in-memory 4-sheet / 5-sheet XLSX files
# ---------------------------------------------------------------------------


def _build_report(
    tmp_path: Path,
    *,
    include_model_sheet: bool = False,
) -> WorkbookReport:
    batches: list[WorkbookBatch] = []
    data = (
        (
            "R1",
            "供应商甲",
            "原竹丝",
            date(2026, 4, 8),
            date(2026, 4, 9),
            ("0.50", "0.52"),
            ScreenStatus.NORMAL,
            DisplayColor.NONE,
            "mean",
            Decimal("1234.5"),
        ),
        (
            "R2",
            "供应商乙",
            "竹丝",
            date(2026, 4, 10),
            date(2026, 4, 11),
            ("0.60",),
            ScreenStatus.HIGH,
            DisplayColor.ORANGE,
            "mean",
            Decimal("900"),
        ),
        (
            "R3",
            "供应商丙",
            "原竹丝",
            date(2026, 4, 12),
            date(2026, 4, 13),
            ("0.45", "0.46"),
            ScreenStatus.LOW,
            DisplayColor.GREEN,
            "minimum",
            Decimal("1100"),
        ),
    )
    for rid, supplier, mat, ad, td, values, status, color, target, weight in data:
        source = tmp_path / f"{rid}.xlsx"
        source.write_bytes(f"source-{rid}".encode())
        samples = tuple(
            SampleMeasurement(
                sample_index=i,
                department_raw="A部门",
                department="A部门",
                source_row=i + 4,
                initial_mass=Decimal("100"),
                dry_mass=Decimal("50"),
                foil_mass=Decimal("4"),
                source_moisture_value=Decimal(v),
                verified_moisture_value=Decimal(v),
                value_used_for_statistics=Decimal(v),
            )
            for i, v in enumerate(values, start=1)
        )
        record = BatchRecord(
            record_id=rid,
            samples=samples,
            source_file=source,
            source_file_hash=f"{rid}" * 21 + "00",
            source_sheet="检测数据",
            supplier=supplier,
            material_type=mat,
            arrival_date=ad,
            test_date=td,
            total_weight_kg=weight,
        )
        decs = [Decimal(v) for v in values]
        m = sum(decs) / len(decs)
        stats = BatchStatistics(
            sample_count=len(decs),
            mean=m,
            total_average=m,
            standard_deviation=Decimal("0.01") if len(decs) > 1 else None,
            minimum=min(decs),
            maximum=max(decs),
            range_value=max(decs) - min(decs),
            median=m,
            first_quartile=min(decs),
            third_quartile=max(decs),
            interquartile_range=max(decs) - min(decs),
            department_averages={"A部门": decs[0]},
            maximum_department_average_difference=Decimal("0"),
        )
        batches.append(
            WorkbookBatch(
                record=record,
                statistics=stats,
                screening_decision=ScreeningDecision(
                    status=status,
                    display_color=color
                    if color in {DisplayColor.ORANGE, DisplayColor.GREEN}
                    else DisplayColor.NONE,
                    target_field=target,
                    reason="确定性初筛",
                ),
                ai_review=AIReviewDecision(
                    status=ReviewStatus.NOT_COMPLETED,
                    display_color=DisplayColor.NONE,
                    confirmation_state=ConfirmationState.NOT_REQUIRED,
                    confidence=None,
                ),
                final_display_color=color,
                confirmation_state=ConfirmationState.NOT_REQUIRED,
                rule_version="rules-v1",
                rule_hash="c" * 64,
                rule_applicable_scope="竹丝/原竹丝；全年",
                rule_confirmation_status="confirmed",
                lower_threshold=Decimal("0.47"),
                upper_threshold=Decimal("0.55"),
                review_suggestion="建议人工复核",
                experience_references=(
                    ExperienceCitation("EXP-001", "1.0", "夏季经验", "exp/001.md"),
                ),
            )
        )
    return WorkbookReport(
        started_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        batches=tuple(batches),
    )


# Monkey-patch to generate 5-sheet XLSX for v1.0.0 testing
def _write_5_sheet(report: WorkbookReport, output_dir: Path) -> Path:
    """Generate a 5-sheet v1.0.0 compatible workbook by adding 模型分析记录."""
    import os
    from uuid import uuid4
    import xlsxwriter

    from moisture.reporting.xlsx_writer import (
        OUTPUT_NAME,
        _formats,
        _ordered_batches,
        _write_anomalies,
        _write_headers,
        _write_summary,
        _write_trace,
        _write_trends,
    )
    from moisture.reporting.labels import (
        color_label,
        confirmation_label,
        review_label,
        screen_label,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / OUTPUT_NAME
    tmp = output_dir / f".summary-{uuid4().hex}.xlsx"
    wb = xlsxwriter.Workbook(tmp, {"strings_to_formulas": False, "strings_to_urls": False})
    formats = _formats(wb)
    _write_summary(wb, report, formats)
    _write_anomalies(wb, report, formats)
    _write_trends(wb, report, formats)
    _write_trace(wb, report, formats)

    # 5th sheet: 模型分析记录
    model_headers = (
        "批次编号",
        "初筛状态",
        "AI复判状态",
        "置信度",
        "最终显示色",
        "人工确认状态",
        "AI理由",
        "降级原因",
    )
    model_ws = wb.add_worksheet("模型分析记录")
    _write_headers(model_ws, model_headers, formats["header"])
    ordered = _ordered_batches(report)
    for r, batch in enumerate(ordered, start=1):
        vals = (
            batch.record.record_id,
            screen_label(batch.screening_decision.status),
            review_label(batch.ai_review.status),
            None,
            color_label(batch.final_display_color),
            confirmation_label(batch.confirmation_state),
            batch.ai_review.rationale,
            batch.ai_degradation_reason,
        )
        for c, v in enumerate(vals):
            fmt = formats["number"] if c == 3 else formats["wrap"]
            if v is None:
                model_ws.write_blank(r, c, None, fmt)
            elif isinstance(v, (int, float)):
                model_ws.write_number(r, c, v, fmt)
            else:
                model_ws.write(r, c, v, fmt)
        model_ws.set_row(r, 36)
    model_ws.set_column(0, 0, 34)
    model_ws.set_column(1, 5, 18)
    model_ws.set_column(6, 7, 36)

    wb.close()
    with tmp.open("r+b") as f:
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, destination)
    return destination


# ---------------------------------------------------------------------------
# Reader tests
# ---------------------------------------------------------------------------


@pytest.fixture
def four_sheet_xlsx(tmp_path: Path) -> Path:
    report = _build_report(tmp_path)
    return write_summary_xlsx(report, tmp_path / "output")


@pytest.fixture
def five_sheet_xlsx(tmp_path: Path) -> Path:
    report = _build_report(tmp_path)
    return _write_5_sheet(report, tmp_path / "output5")


class TestFourSheetReader:
    def test_reads_format_version(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        assert snap.format_version == SummaryFormat.V1_0_1_FOUR_SHEET

    def test_reads_all_batches(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        assert len(snap.batches) == 3
        assert [b.record.record_id for b in snap.batches] == ["R1", "R2", "R3"]

    def test_reads_supplier_and_material(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        assert snap.batches[0].record.supplier == "供应商甲"
        assert snap.batches[0].record.material_type == "原竹丝"

    def test_reads_dates(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        assert snap.batches[0].record.arrival_date == date(2026, 4, 8)
        assert snap.batches[0].record.test_date == date(2026, 4, 9)

    def test_reads_sample_values(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        b1 = snap.batches[0]
        assert len(b1.record.samples) == 2
        assert b1.record.samples[0].value_used_for_statistics == Decimal("0.50")
        assert b1.record.samples[1].value_used_for_statistics == Decimal("0.52")

    def test_reads_single_sample_batch(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        b2 = snap.batches[1]
        assert len(b2.record.samples) == 1
        assert b2.record.samples[0].value_used_for_statistics == Decimal("0.60")

    def test_reads_statistics(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        b1 = snap.batches[0]
        assert b1.statistics.mean is not None
        assert b1.statistics.minimum is not None
        assert b1.statistics.maximum is not None

    def test_reads_source_trace(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        b1 = snap.batches[0]
        assert b1.record.source_file_hash != ""
        assert b1.record.samples[0].source_row == 5
        assert b1.record.samples[0].department == "A部门"
        assert b1.rule_hash == "c" * 64
        assert b1.rule_confirmation_status == "confirmed"
        assert [(item.entry_id, item.version) for item in b1.experience_references] == [
            ("EXP-001", "1.0")
        ]

    def test_reads_thresholds(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        b1 = snap.batches[0]
        assert b1.lower_threshold is not None
        assert b1.upper_threshold is not None

    def test_reads_high_low_normal_status(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        colors = [b.final_display_color for b in snap.batches]
        assert colors == [DisplayColor.NONE, DisplayColor.ORANGE, DisplayColor.GREEN]

    def test_source_sha256_is_stable(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        s1 = reader.read(four_sheet_xlsx)
        s2 = reader.read(four_sheet_xlsx)
        assert s1.source_sha256 == s2.source_sha256

    def test_display_name_is_file_name(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(four_sheet_xlsx)
        assert snap.source_display_name == "moisture_summary.xlsx"

    def test_batches_are_stable(self, four_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        s1 = reader.read(four_sheet_xlsx)
        s2 = reader.read(four_sheet_xlsx)
        assert s1.batches == s2.batches


class TestFiveSheetReader:
    def test_reads_format_version(self, five_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(five_sheet_xlsx)
        assert snap.format_version == SummaryFormat.V1_0_0_FIVE_SHEET

    def test_reads_all_batches(self, five_sheet_xlsx: Path) -> None:
        reader = StandardSummaryReader()
        snap = reader.read(five_sheet_xlsx)
        assert len(snap.batches) == 3


class TestValidation:
    def test_non_xlsx_rejected(self, tmp_path: Path) -> None:
        path = tmp_path / "not.xlsx"
        path.write_text("not an xlsx")
        reader = StandardSummaryReader()
        with pytest.raises(ValueError, match=".xlsx"):
            reader.read(path)

    def test_wrong_sheets_rejected(self, tmp_path: Path) -> None:
        import xlsxwriter

        path = tmp_path / "bad.xlsx"
        wb = xlsxwriter.Workbook(path)
        wb.add_worksheet("Wrong")
        wb.close()
        reader = StandardSummaryReader()
        with pytest.raises(ValueError, match="standard"):
            reader.read(path)
