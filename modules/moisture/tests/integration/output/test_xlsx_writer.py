from __future__ import annotations

# ruff: noqa: E402, I001

import re
import sys
from contextlib import closing
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import openpyxl
import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

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
from moisture.ports.writers import ExperienceCitation, WorkbookBatch, WorkbookReport
from moisture.reporting import xlsx_writer
from moisture.reporting.xlsx_writer import COLOR_HEX, write_summary_xlsx

SHEET_NAMES = [
    "竹丝含水率统计",
    "异常分析明细",
    "趋势分析",
    "来源追溯",
    "模型分析记录",
]


def _record(record_id: str, source: Path, values: tuple[str, ...]) -> BatchRecord:
    samples = tuple(
        SampleMeasurement(
            sample_index=index,
            department_raw="品质" if index == 1 else "二厂",
            department="品质" if index == 1 else "二厂",
            source_row=index + 4,
            initial_mass=Decimal("100"),
            dry_mass=Decimal("52"),
            foil_mass=Decimal("4"),
            source_moisture_value=Decimal(value),
            verified_moisture_value=Decimal(value),
            value_used_for_statistics=Decimal(value),
        )
        for index, value in enumerate(values, start=1)
    )
    return BatchRecord(
        record_id=record_id,
        samples=samples,
        source_file=source,
        source_file_hash=("a" if record_id == "R1" else "b") * 64,
        source_sheet="检测数据",
        supplier="供应商甲",
        material_type="竹丝",
        arrival_date=date(2026, 7, 12),
        test_date=date(2026, 7, 13),
        total_weight_kg=Decimal("1234.5"),
    )


def _statistics(values: tuple[str, ...]) -> BatchStatistics:
    decimals = [Decimal(value) for value in values]
    mean = sum(decimals, start=Decimal("0")) / Decimal(len(decimals))
    return BatchStatistics(
        sample_count=len(decimals),
        mean=mean,
        total_average=mean,
        standard_deviation=Decimal("0.014142"),
        minimum=min(decimals),
        maximum=max(decimals),
        range_value=max(decimals) - min(decimals),
        median=mean,
        first_quartile=min(decimals),
        third_quartile=max(decimals),
        interquartile_range=max(decimals) - min(decimals),
        department_averages={"品质": decimals[0], "二厂": decimals[-1]},
        maximum_department_average_difference=max(decimals) - min(decimals),
    )


@pytest.fixture
def report(tmp_path: Path) -> WorkbookReport:
    batches: list[WorkbookBatch] = []
    settings = (
        ("R1", ("0.60", "0.62"), ScreenStatus.HIGH, DisplayColor.ORANGE, "mean"),
        ("R2", ("0.45", "0.46"), ScreenStatus.LOW, DisplayColor.GREEN, "minimum"),
        ("R3", ("0.57", "0.58"), ScreenStatus.HIGH, DisplayColor.RED, "maximum"),
        ("R4", ("0.43", "0.44"), ScreenStatus.LOW, DisplayColor.BLUE, "sample_1"),
    )
    for record_id, values, status, color, target in settings:
        source = tmp_path / f"{record_id}.xlsx"
        source.write_bytes(f"unchanged-{record_id}".encode())
        record = _record(record_id, source, values)
        batches.append(
            WorkbookBatch(
                record=record,
                statistics=_statistics(values),
                screening_decision=ScreeningDecision(
                    status=status,
                    display_color=color
                    if color in {DisplayColor.ORANGE, DisplayColor.GREEN}
                    else DisplayColor.ORANGE,
                    target_field=target,
                    reason="确定性初筛疑似",
                ),
                ai_review=AIReviewDecision(
                    status=(
                        ReviewStatus.REVIEW_HIGH
                        if color == DisplayColor.RED
                        else ReviewStatus.REVIEW_LOW
                        if color == DisplayColor.BLUE
                        else ReviewStatus.NOT_COMPLETED
                    ),
                    display_color=color
                    if color in {DisplayColor.RED, DisplayColor.BLUE}
                    else DisplayColor.NONE,
                    confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
                    target_field=target if color in {DisplayColor.RED, DisplayColor.BLUE} else None,
                    confidence=Decimal("0.86")
                    if color in {DisplayColor.RED, DisplayColor.BLUE}
                    else None,
                    rationale="高度疑似，非正式错误结论"
                    if color in {DisplayColor.RED, DisplayColor.BLUE}
                    else None,
                ),
                final_display_color=color,
                confirmation_state=ConfirmationState.PENDING_HUMAN_REVIEW,
                rule_version="rules-v1",
                lower_threshold=Decimal("0.47"),
                upper_threshold=Decimal("0.55"),
                review_suggestion="建议人工复核，不构成正式判定",
                experience_references=(
                    ExperienceCitation(
                        "EXP-001", "1.2.0", "夏季竹丝复核经验", "experience/exp-001.md"
                    ),
                ),
                ai_degradation_reason="AI 未授权"
                if color in {DisplayColor.ORANGE, DisplayColor.GREEN}
                else None,
            )
        )
    return WorkbookReport(
        started_at=datetime(2026, 7, 13, 8, 0, tzinfo=UTC),
        batches=tuple(batches),
    )


def test_workbook_contains_five_required_sheets(tmp_path: Path, report: WorkbookReport) -> None:
    output = write_summary_xlsx(report, tmp_path / "output")

    assert output == tmp_path / "output" / "moisture_summary.xlsx"
    with closing(openpyxl.load_workbook(output, data_only=False)) as workbook:
        assert workbook.sheetnames == SHEET_NAMES
        summary = workbook[SHEET_NAMES[0]]
        headers = [cell.value for cell in summary[1]]
        assert headers[headers.index("样本1") : headers.index("样本1") + 10] == [
            f"样本{index}" for index in range(1, 11)
        ]
        assert summary.auto_filter.ref == f"A1:{summary.cell(1, summary.max_column).column_letter}1"
        assert summary.freeze_panes == "C2"
        assert summary.cell(2, headers.index("均值") + 1).value == pytest.approx(0.61)
        assert summary.cell(2, headers.index("来源文件") + 1).value == "R1.xlsx"
        assert summary.cell(2, headers.index("来源工作表") + 1).value == "检测数据"
        assert summary.cell(2, headers.index("均值") + 1).number_format == "0.00%"
        assert summary.cell(2, headers.index("总重(kg)") + 1).number_format == "#,##0.0"


def test_review_colors_match_contract_semantics(tmp_path: Path, report: WorkbookReport) -> None:
    output = write_summary_xlsx(report, tmp_path / "output")
    with closing(openpyxl.load_workbook(output, data_only=False)) as workbook:
        sheet = workbook[SHEET_NAMES[0]]
        headers = [cell.value for cell in sheet[1]]
        targets = ("均值", "最小值", "最大值", "样本1")
        colors = ("orange", "green", "red", "blue")
        for row, target, color in zip(range(2, 6), targets, colors, strict=True):
            assert (
                sheet.cell(row, headers.index(target) + 1).fill.fgColor.rgb
                == f"FF{COLOR_HEX[color]}"
            )


def test_workbook_has_named_charts_and_plain_untrusted_text(
    tmp_path: Path, report: WorkbookReport
) -> None:
    first = report.batches[0]
    unsafe_record = replace(first.record, supplier='=HYPERLINK("https://invalid.example","x")')
    unsafe_report = WorkbookReport(
        started_at=report.started_at,
        batches=(replace(first, record=unsafe_record), *report.batches[1:]),
    )
    output = write_summary_xlsx(unsafe_report, tmp_path / "output")

    with ZipFile(output) as archive:
        chart_xml = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.startswith("xl/charts/chart")
        )
    assert "来料平均含水率散点图" in chart_xml
    assert "区间值趋势图" in chart_xml

    with closing(openpyxl.load_workbook(output, data_only=False)) as workbook:
        sheet = workbook[SHEET_NAMES[0]]
        headers = [cell.value for cell in sheet[1]]
        supplier = sheet.cell(2, headers.index("供应商") + 1)
        assert supplier.value == '=HYPERLINK("https://invalid.example","x")'
        assert supplier.data_type == "s"
        error_pattern = re.compile(r"#(?:REF!|DIV/0!|VALUE!|NAME\?|N/A)")
        assert all(
            not (isinstance(cell.value, str) and error_pattern.search(cell.value))
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
        )


def test_workbook_is_deterministic(tmp_path: Path, report: WorkbookReport) -> None:
    first = write_summary_xlsx(report, tmp_path / "first")
    second = write_summary_xlsx(report, tmp_path / "second")

    assert first.read_bytes() == second.read_bytes()


def test_xlsx_is_replaced_atomically(
    tmp_path: Path, report: WorkbookReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    final = output_dir / "moisture_summary.xlsx"
    final.write_bytes(b"previous-valid-report")

    def fail_validation(path: Path) -> None:
        assert path.parent == output_dir
        assert path.name.startswith(".moisture_summary-")
        assert path.suffix == ".xlsx"
        raise ValueError("synthetic validation failure")

    monkeypatch.setattr(xlsx_writer, "validate_workbook", fail_validation)

    with pytest.raises(ValueError, match="synthetic validation failure"):
        write_summary_xlsx(report, output_dir)

    assert final.read_bytes() == b"previous-valid-report"
    assert not list(output_dir.glob(".moisture_summary-*.xlsx"))


def test_generation_failure_leaves_no_formal_or_temporary_output(
    tmp_path: Path, report: WorkbookReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_summary(*args: object) -> None:
        raise RuntimeError("synthetic generation failure")

    monkeypatch.setattr(xlsx_writer, "_write_summary", fail_summary)
    output_dir = tmp_path / "output"

    with pytest.raises(RuntimeError, match="synthetic generation failure"):
        write_summary_xlsx(report, output_dir)

    assert not (output_dir / "moisture_summary.xlsx").exists()
    assert not list(output_dir.glob(".moisture_summary-*.xlsx"))


def test_writer_does_not_modify_input_files(tmp_path: Path, report: WorkbookReport) -> None:
    before = {
        batch.record.source_file: batch.record.source_file.read_bytes() for batch in report.batches
    }

    write_summary_xlsx(report, tmp_path / "output")

    assert {path: path.read_bytes() for path in before} == before
