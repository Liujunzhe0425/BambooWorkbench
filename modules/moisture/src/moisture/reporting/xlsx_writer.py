"""Atomic five-sheet XLSX summary writer migrated from the stable baseline."""

from __future__ import annotations

import os
import sys
from contextlib import suppress
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import xlsxwriter
from moisture.domain.enums import DisplayColor
from moisture.ports.writers import WorkbookBatch, WorkbookReport
from moisture.reporting.workbook_validation import REQUIRED_SHEET_NAMES, validate_workbook

COLOR_HEX: dict[str, str | None] = {
    "orange": "F4B183",
    "green": "A9D18E",
    "red": "FF0000",
    "blue": "5B9BD5",
    "none": None,
}

SHEET_NAMES = REQUIRED_SHEET_NAMES
OUTPUT_NAME = "moisture_summary.xlsx"

SUMMARY_HEADERS = (
    "序号",
    "批次编号",
    "供应商",
    "材料类型",
    "到货日期",
    "检测日期",
    "总重(kg)",
    *(f"样本{index}" for index in range(1, 11)),
    "样本部门映射",
    "最大值",
    "最小值",
    "区间值",
    "均值",
    "标准差",
    "中位数",
    "第一四分位数",
    "第三四分位数",
    "四分位距",
    "部门均值最大差",
    "初筛下限",
    "初筛上限",
    "规则版本",
    "初筛状态",
    "AI复判状态",
    "置信度",
    "最终显示色",
    "人工确认状态",
    "复核建议",
    "来源文件",
    "来源工作表",
)

TARGET_HEADERS = {
    "mean": "均值",
    "total_average": "均值",
    "range_value": "区间值",
    "minimum": "最小值",
    "maximum": "最大值",
    "standard_deviation": "标准差",
    "median": "中位数",
    "first_quartile": "第一四分位数",
    "third_quartile": "第三四分位数",
    "interquartile_range": "四分位距",
    "maximum_department_average_difference": "部门均值最大差",
    "total_weight_kg": "总重(kg)",
}


def _number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _excel_date(value: date | None) -> datetime | None:
    return None if value is None else datetime.combine(value, time.min)


def _target_header(batch: WorkbookBatch) -> str | None:
    decision = (
        batch.ai_review
        if batch.ai_review.display_color != DisplayColor.NONE
        else batch.screening_decision
    )
    target = decision.target_field
    if target is None:
        return None
    if target.startswith("sample_") and target.removeprefix("sample_").isdigit():
        sample_index = int(target.removeprefix("sample_"))
        return f"样本{sample_index}" if 1 <= sample_index <= 10 else None
    return TARGET_HEADERS.get(target)


def _write_headers(worksheet: Any, headers: tuple[str, ...], header_format: Any) -> None:
    for column, header in enumerate(headers):
        worksheet.write(0, column, header, header_format)
    worksheet.freeze_panes(1, 2)
    worksheet.autofilter(0, 0, 0, len(headers) - 1)
    worksheet.hide_gridlines(2)


def _formats(workbook: Any) -> dict[str, Any]:
    formats: dict[str, Any] = {
        "header": workbook.add_format(
            {
                "bold": True,
                "font_color": "FFFFFF",
                "bg_color": "4472C4",
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "text": workbook.add_format({"align": "left", "valign": "vcenter"}),
        "center": workbook.add_format({"align": "center", "valign": "vcenter"}),
        "number": workbook.add_format({"num_format": "0.00%", "align": "right"}),
        "weight": workbook.add_format({"num_format": "#,##0.0", "align": "right"}),
        "date": workbook.add_format({"num_format": "yyyy-mm-dd", "align": "center"}),
        "wrap": workbook.add_format({"text_wrap": True, "valign": "top"}),
    }
    for name, color in COLOR_HEX.items():
        if color is not None:
            formats[f"color_{name}"] = workbook.add_format(
                {
                    "num_format": "0.00%",
                    "bg_color": color,
                    "pattern": 1,
                    "align": "right",
                }
            )
            formats[f"color_{name}_weight"] = workbook.add_format(
                {
                    "num_format": "#,##0.0",
                    "bg_color": color,
                    "pattern": 1,
                    "align": "right",
                }
            )
    return formats


def _summary_row(batch: WorkbookBatch, index: int) -> list[object | None]:
    sample_values: list[object | None] = [
        _number(sample.value_used_for_statistics) for sample in batch.record.samples
    ]
    sample_values.extend([None] * (10 - len(sample_values)))
    department_map = "; ".join(
        f"样本{sample.sample_index}:{sample.department}" for sample in batch.record.samples
    )
    return [
        index,
        batch.record.record_id,
        batch.record.supplier,
        batch.record.material_type,
        _excel_date(batch.record.arrival_date),
        _excel_date(batch.record.test_date),
        _number(batch.record.total_weight_kg),
        *sample_values,
        department_map,
        _number(batch.statistics.maximum),
        _number(batch.statistics.minimum),
        _number(batch.statistics.range_value),
        _number(batch.statistics.mean),
        _number(batch.statistics.standard_deviation),
        _number(batch.statistics.median),
        _number(batch.statistics.first_quartile),
        _number(batch.statistics.third_quartile),
        _number(batch.statistics.interquartile_range),
        _number(batch.statistics.maximum_department_average_difference),
        _number(batch.lower_threshold),
        _number(batch.upper_threshold),
        batch.rule_version,
        batch.screening_decision.status.value,
        batch.ai_review.status.value,
        _number(batch.ai_review.confidence),
        batch.final_display_color.value,
        batch.confirmation_state.value,
        batch.review_suggestion,
        batch.record.source_file.name if batch.record.source_file else None,
        batch.record.source_sheet,
    ]


def _write_summary(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    worksheet = workbook.add_worksheet(SHEET_NAMES[0])
    _write_headers(worksheet, SUMMARY_HEADERS, formats["header"])
    worksheet.set_row(0, 26)
    worksheet.set_column(0, 1, 13)
    worksheet.set_column(2, 3, 15)
    worksheet.set_column(4, 5, 12)
    worksheet.set_column(6, 16, 11)
    worksheet.set_column(17, 17, 30)
    worksheet.set_column(18, 29, 13)
    worksheet.set_column(30, 35, 16)
    worksheet.set_column(36, 36, 28)
    worksheet.set_column(37, 38, 20)
    columns = {header: index for index, header in enumerate(SUMMARY_HEADERS)}
    date_columns = {columns["到货日期"], columns["检测日期"]}
    percent_headers = {
        *(f"样本{index}" for index in range(1, 11)),
        "最大值",
        "最小值",
        "区间值",
        "均值",
        "标准差",
        "中位数",
        "第一四分位数",
        "第三四分位数",
        "四分位距",
        "部门均值最大差",
        "初筛下限",
        "初筛上限",
        "置信度",
    }
    percent_columns = {columns[name] for name in percent_headers}
    for row_index, batch in enumerate(report.batches, start=1):
        target_header = _target_header(batch)
        for column, value in enumerate(_summary_row(batch, row_index)):
            cell_format = formats["text"]
            if column in date_columns:
                cell_format = formats["date"]
            elif column in percent_columns:
                cell_format = formats["number"]
            elif column == columns["总重(kg)"]:
                cell_format = formats["weight"]
            elif column in {columns["复核建议"], columns["样本部门映射"]}:
                cell_format = formats["wrap"]
            if target_header is not None and column == columns[target_header]:
                color_key = f"color_{batch.final_display_color.value}"
                if column == columns["总重(kg)"]:
                    color_key = f"{color_key}_weight"
                cell_format = formats.get(color_key, cell_format)
            if value is None:
                worksheet.write_blank(row_index, column, None, cell_format)
            elif isinstance(value, datetime):
                worksheet.write_datetime(row_index, column, value, cell_format)
            elif isinstance(value, (int, float)):
                worksheet.write_number(row_index, column, value, cell_format)
            else:
                worksheet.write(row_index, column, value, cell_format)
        worksheet.set_row(row_index, 30)


def _write_anomalies(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = ("批次编号", "目标字段", "初筛状态", "AI复判状态", "最终显示色", "原因", "复核建议")
    worksheet = workbook.add_worksheet(SHEET_NAMES[1])
    _write_headers(worksheet, headers, formats["header"])
    row = 1
    for batch in report.batches:
        if batch.final_display_color == DisplayColor.NONE:
            continue
        values = (
            batch.record.record_id,
            batch.ai_review.target_field or batch.screening_decision.target_field,
            batch.screening_decision.status.value,
            batch.ai_review.status.value,
            batch.final_display_color.value,
            batch.ai_review.rationale or batch.screening_decision.reason,
            batch.review_suggestion,
        )
        for column, value in enumerate(values):
            worksheet.write(row, column, value, formats["wrap"] if column >= 5 else formats["text"])
        row += 1
    worksheet.set_column(0, 4, 18)
    worksheet.set_column(5, 6, 34)


def _write_trends(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = ("序号", "批次编号", "检测日期", "供应商", "均值", "区间值", "初筛下限", "初筛上限")
    worksheet = workbook.add_worksheet(SHEET_NAMES[2])
    _write_headers(worksheet, headers, formats["header"])
    for row_index, batch in enumerate(report.batches, start=1):
        values = (
            row_index,
            batch.record.record_id,
            _excel_date(batch.record.test_date),
            batch.record.supplier,
            _number(batch.statistics.mean),
            _number(batch.statistics.range_value),
            _number(batch.lower_threshold),
            _number(batch.upper_threshold),
        )
        for column, value in enumerate(values):
            if isinstance(value, datetime):
                worksheet.write_datetime(row_index, column, value, formats["date"])
            elif isinstance(value, (int, float)):
                worksheet.write_number(
                    row_index,
                    column,
                    value,
                    formats["number"] if column >= 4 else formats["center"],
                )
            else:
                worksheet.write(row_index, column, value, formats["text"])
    worksheet.set_column(0, 1, 14)
    worksheet.set_column(2, 3, 16)
    worksheet.set_column(4, 7, 13)
    if not report.batches:
        return
    last_row = len(report.batches)
    average_chart = workbook.add_chart({"type": "scatter", "subtype": "straight_with_markers"})
    for column, name, color in (
        (4, "批次均值", "4472C4"),
        (7, "初筛上限", COLOR_HEX["orange"] or "F4B183"),
        (6, "初筛下限", COLOR_HEX["green"] or "A9D18E"),
    ):
        series: dict[str, Any] = {
            "name": name,
            "categories": [SHEET_NAMES[2], 1, 0, last_row, 0],
            "values": [SHEET_NAMES[2], 1, column, last_row, column],
            "line": {"color": color},
            "marker": {"type": "circle", "size": 5},
        }
        if column == 4:
            series["trendline"] = {
                "type": "linear",
                "name": "总体趋势",
                "line": {"color": "7F7F7F", "dash_type": "dash"},
            }
        average_chart.add_series(series)
    average_chart.set_title({"name": "来料平均含水率散点图"})
    average_chart.set_x_axis({"name": "检测批次"})
    average_chart.set_y_axis({"name": "含水率", "num_format": "0.0%"})
    average_chart.set_legend({"position": "bottom"})
    average_chart.set_style(10)
    worksheet.insert_chart("K2", average_chart, {"x_scale": 1.35, "y_scale": 1.2})

    range_chart = workbook.add_chart({"type": "line"})
    range_chart.add_series(
        {
            "name": "区间值",
            "categories": [SHEET_NAMES[2], 1, 1, last_row, 1],
            "values": [SHEET_NAMES[2], 1, 5, last_row, 5],
            "line": {"color": "70AD47", "width": 2},
            "marker": {"type": "diamond", "size": 5},
        }
    )
    range_chart.set_title({"name": "区间值趋势图"})
    range_chart.set_x_axis({"name": "检测批次"})
    range_chart.set_y_axis({"name": "区间值", "num_format": "0.0%"})
    range_chart.set_legend({"none": True})
    range_chart.set_style(10)
    worksheet.insert_chart("K20", range_chart, {"x_scale": 1.35, "y_scale": 1.2})


def _write_trace(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = ("批次编号", "来源文件", "文件哈希", "来源工作表", "样本行", "规则版本", "经验引用")
    worksheet = workbook.add_worksheet(SHEET_NAMES[3])
    _write_headers(worksheet, headers, formats["header"])
    for row, batch in enumerate(report.batches, start=1):
        values = (
            batch.record.record_id,
            str(batch.record.source_file) if batch.record.source_file else None,
            batch.record.source_file_hash,
            batch.record.source_sheet,
            ", ".join(str(sample.source_row) for sample in batch.record.samples),
            batch.rule_version,
            "; ".join(f"{item.entry_id} v{item.version}" for item in batch.experience_references),
        )
        for column, value in enumerate(values):
            worksheet.write(
                row, column, value, formats["wrap"] if column in {1, 2, 6} else formats["text"]
            )
    worksheet.set_column(0, 0, 16)
    worksheet.set_column(1, 1, 28)
    worksheet.set_column(2, 2, 68)
    worksheet.set_column(3, 6, 22)


def _write_model_records(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = ("批次编号", "AI复判状态", "置信度", "目标字段", "理由", "降级原因", "人工确认状态")
    worksheet = workbook.add_worksheet(SHEET_NAMES[4])
    _write_headers(worksheet, headers, formats["header"])
    for row, batch in enumerate(report.batches, start=1):
        values = (
            batch.record.record_id,
            batch.ai_review.status.value,
            _number(batch.ai_review.confidence),
            batch.ai_review.target_field,
            batch.ai_review.rationale,
            batch.ai_degradation_reason,
            batch.confirmation_state.value,
        )
        for column, value in enumerate(values):
            cell_format = formats["number"] if column == 2 else formats["wrap"]
            if value is None:
                worksheet.write_blank(row, column, None, cell_format)
            elif isinstance(value, (int, float)):
                worksheet.write_number(row, column, value, cell_format)
            else:
                worksheet.write(row, column, value, cell_format)
    worksheet.set_column(0, 3, 18)
    worksheet.set_column(4, 5, 36)
    worksheet.set_column(6, 6, 22)


def write_summary_xlsx(report: WorkbookReport, output_dir: Path) -> Path:
    """Write, validate, and atomically replace the formal workbook."""

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / OUTPUT_NAME
    temporary = output_dir / f".moisture_summary-{uuid4().hex}.xlsx"
    workbook: Any | None = None
    try:
        workbook = xlsxwriter.Workbook(
            temporary,
            {"strings_to_formulas": False, "strings_to_urls": False},
        )
        workbook.set_properties(
            {
                "title": "竹丝含水率确定性分析汇总",
                "author": "moisture",
                "created": report.started_at.replace(tzinfo=None),
            }
        )
        formats = _formats(workbook)
        _write_summary(workbook, report, formats)
        _write_anomalies(workbook, report, formats)
        _write_trends(workbook, report, formats)
        _write_trace(workbook, report, formats)
        _write_model_records(workbook, report, formats)
        workbook.close()
        workbook = None
        validate_workbook(temporary)
        with temporary.open("r+b") as output:
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        return destination
    finally:
        cleanup_follows_error = sys.exc_info()[0] is not None
        if workbook is not None:
            with suppress(Exception):
                workbook.close()
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            if not cleanup_follows_error:
                raise


class XlsxWriter:
    """Adapter implementing the narrow summary writer port."""

    def write(self, report: WorkbookReport, output_dir: Path) -> Path:
        return write_summary_xlsx(report, output_dir)
