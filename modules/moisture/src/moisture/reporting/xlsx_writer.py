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
from moisture.domain.enums import DisplayColor, ScreenStatus
from moisture.domain.models import ScreeningDecision
from moisture.ports.writers import WorkbookBatch, WorkbookReport
from moisture.reporting.labels import (
    color_label,
    confirmation_label,
    review_label,
    screen_label,
)
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
    "供应商",
    "材料类型",
    "到货日期",
    "检测日期",
    *(f"样本{index}" for index in range(1, 11)),
    "最大值",
    "最小值",
    "区间值",
    "均值",
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


def _target_header_for(target: str | None) -> str | None:
    if target is None:
        return None
    if target.startswith("sample_") and target.removeprefix("sample_").isdigit():
        sample_index = int(target.removeprefix("sample_"))
        return f"样本{sample_index}" if 1 <= sample_index <= 10 else None
    return TARGET_HEADERS.get(target)


def _target_header(batch: WorkbookBatch) -> str | None:
    decision = (
        batch.ai_review
        if batch.ai_review.display_color != DisplayColor.NONE
        else batch.screening_decision
    )
    return _target_header_for(decision.target_field)


def _screen_result(batch: WorkbookBatch) -> str:
    if batch.screening_decision.status == ScreenStatus.DATA_QUALITY:
        return "需人工确认"
    return screen_label(batch.screening_decision.status)


def _material_label(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized in {"竹丝", "原竹丝"}:
        return "原竹丝"
    return normalized


def _ordered_batches(report: WorkbookReport) -> tuple[WorkbookBatch, ...]:
    """Return batches in stable display order without modifying the original report.

    Sort key: test_date ASC → arrival_date fallback → missing last
             → record_id → source_sha256
    """
    from datetime import MAXYEAR

    _date_max = date(MAXYEAR, 12, 31)

    def _sort_key(batch: WorkbookBatch) -> tuple[int, date, str, str]:
        record = batch.record
        observed = record.test_date or record.arrival_date
        return (
            1 if observed is None else 0,
            observed or _date_max,
            record.record_id or "",
            record.source_file_hash or "",
        )

    return tuple(sorted(report.batches, key=_sort_key))


def _department_map(batch: WorkbookBatch) -> str:
    return "; ".join(
        f"样本{sample.sample_index}:{sample.department}" for sample in batch.record.samples
    )


def _target_value_for(batch: WorkbookBatch, target: str | None) -> Decimal | None:
    if target is None:
        return None
    if target.startswith("sample_") and target.removeprefix("sample_").isdigit():
        sample_index = int(target.removeprefix("sample_"))
        for sample in batch.record.samples:
            if sample.sample_index == sample_index:
                return sample.value_used_for_statistics
        return None
    if target == "total_weight_kg":
        return batch.record.total_weight_kg
    return getattr(batch.statistics, target, None)


def _target_value(batch: WorkbookBatch) -> Decimal | None:
    decision = (
        batch.ai_review
        if batch.ai_review.display_color != DisplayColor.NONE
        else batch.screening_decision
    )
    return _target_value_for(batch, decision.target_field)


def _target_colors(batch: WorkbookBatch) -> dict[str, DisplayColor]:
    colors: dict[str, DisplayColor] = {}
    for decision in batch.screening_decisions or (batch.screening_decision,):
        header = _target_header_for(decision.target_field)
        if header is not None and decision.display_color is not DisplayColor.NONE:
            colors[header] = decision.display_color
    if batch.ai_review.display_color is not DisplayColor.NONE:
        header = _target_header_for(batch.ai_review.target_field)
        if header is not None:
            colors[header] = batch.ai_review.display_color
    return colors


def _anomaly_suggestion(batch: WorkbookBatch, decision: ScreeningDecision) -> str:
    if decision.target_field == "range_value":
        return "建议复核样本离散程度、取样和称量记录"
    if decision == batch.screening_decision:
        return batch.review_suggestion
    return decision.reason or batch.review_suggestion


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
        "main_header": workbook.add_format(
            {
                "bold": True,
                "font_color": "1F4E3D",
                "bg_color": "E2F0D9",
                "border": 1,
                "border_color": "A6A6A6",
                "align": "center",
                "valign": "vcenter",
            }
        ),
        "main_text": workbook.add_format(
            {"border": 1, "border_color": "D9D9D9", "align": "left", "valign": "vcenter"}
        ),
        "main_center": workbook.add_format(
            {"border": 1, "border_color": "D9D9D9", "align": "center", "valign": "vcenter"}
        ),
        "main_number": workbook.add_format(
            {
                "num_format": "0.00%",
                "border": 1,
                "border_color": "D9D9D9",
                "align": "right",
                "valign": "vcenter",
            }
        ),
        "main_date": workbook.add_format(
            {
                "num_format": "yyyy-mm-dd",
                "border": 1,
                "border_color": "D9D9D9",
                "align": "center",
                "valign": "vcenter",
            }
        ),
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
            formats[f"main_color_{name}_number"] = workbook.add_format(
                {
                    "num_format": "0.00%",
                    "bg_color": color,
                    "pattern": 1,
                    "border": 1,
                    "border_color": "D9D9D9",
                    "align": "right",
                    "valign": "vcenter",
                }
            )
            formats[f"main_color_{name}_text"] = workbook.add_format(
                {
                    "bg_color": color,
                    "pattern": 1,
                    "border": 1,
                    "border_color": "D9D9D9",
                    "align": "center",
                    "valign": "vcenter",
                }
            )
    return formats


def _summary_row(batch: WorkbookBatch, index: int) -> list[object | None]:
    sample_values: list[object | None] = [
        _number(sample.value_used_for_statistics) for sample in batch.record.samples
    ]
    sample_values.extend([None] * (10 - len(sample_values)))
    return [
        index,
        batch.record.supplier,
        _material_label(batch.record.material_type),
        _excel_date(batch.record.arrival_date),
        _excel_date(batch.record.test_date),
        *sample_values,
        _number(batch.statistics.maximum),
        _number(batch.statistics.minimum),
        _number(batch.statistics.range_value),
        _number(batch.statistics.mean),
    ]


def _write_summary(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    worksheet = workbook.add_worksheet(SHEET_NAMES[0])
    _write_headers(worksheet, SUMMARY_HEADERS, formats["main_header"])
    worksheet.freeze_panes(1, 5)
    worksheet.set_row(0, 26)
    worksheet.set_column(0, 0, 8)
    worksheet.set_column(1, 2, 16)
    worksheet.set_column(3, 4, 12)
    worksheet.set_column(5, 14, 11)
    worksheet.set_column(15, 18, 12)
    columns = {header: index for index, header in enumerate(SUMMARY_HEADERS)}
    date_columns = {columns["到货日期"], columns["检测日期"]}
    percent_headers = {
        *(f"样本{index}" for index in range(1, 11)),
        "最大值",
        "最小值",
        "区间值",
        "均值",
    }
    percent_columns = {columns[name] for name in percent_headers}
    ordered = _ordered_batches(report)
    for row_index, batch in enumerate(ordered, start=1):
        target_colors = _target_colors(batch)
        for column, value in enumerate(_summary_row(batch, row_index)):
            cell_format = formats["main_text"]
            if column in date_columns:
                cell_format = formats["main_date"]
            elif column in percent_columns:
                cell_format = formats["main_number"]
            elif column in {columns["序号"], columns["材料类型"]}:
                cell_format = formats["main_center"]
            header = SUMMARY_HEADERS[column]
            if header in target_colors:
                color_key = f"main_color_{target_colors[header].value}_number"
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
    headers = (
        "批次编号",
        "供应商",
        "检测日期",
        "目标字段",
        "观测值",
        "筛查结果",
        "原因",
        "复核建议",
    )
    worksheet = workbook.add_worksheet(SHEET_NAMES[1])
    _write_headers(worksheet, headers, formats["header"])
    row = 1
    for batch in _ordered_batches(report):
        for decision in batch.screening_decisions or (batch.screening_decision,):
            if decision.display_color is DisplayColor.NONE:
                continue
            target_header = _target_header_for(decision.target_field)
            reviewed = (
                batch.ai_review.display_color is not DisplayColor.NONE
                and batch.ai_review.target_field == decision.target_field
            )
            values = (
                batch.record.record_id,
                batch.record.supplier,
                _excel_date(batch.record.test_date),
                target_header or decision.target_field,
                _number(_target_value_for(batch, decision.target_field)),
                (
                    _screen_result(batch)
                    if decision == batch.screening_decision
                    else screen_label(decision.status)
                ),
                batch.ai_review.rationale if reviewed else decision.reason,
                _anomaly_suggestion(batch, decision),
            )
            for column, value in enumerate(values):
                cell_format = formats["wrap"] if column >= 6 else formats["text"]
                if isinstance(value, datetime):
                    worksheet.write_datetime(row, column, value, formats["date"])
                elif isinstance(value, (int, float)):
                    number_format = (
                        formats["weight"]
                        if column == 4 and target_header == "总重(kg)"
                        else formats["number"]
                    )
                    worksheet.write_number(row, column, value, number_format)
                else:
                    worksheet.write(row, column, value, cell_format)
            worksheet.set_row(row, 30)
            row += 1
    worksheet.set_column(0, 0, 34)
    worksheet.set_column(1, 1, 14)
    worksheet.set_column(2, 2, 12)
    worksheet.set_column(3, 5, 14)
    worksheet.set_column(6, 7, 34)


def _write_trends(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = (
        "序号", "批次编号", "检测日期", "供应商", "均值", "区间值", "初筛下限", "初筛上限",
        "标准差", "中位数", "第一四分位数", "第三四分位数", "四分位距", "部门均值最大差",
    )
    worksheet = workbook.add_worksheet(SHEET_NAMES[2])
    _write_headers(worksheet, headers, formats["header"])
    ordered = _ordered_batches(report)
    for row_index, batch in enumerate(ordered, start=1):
        values = (
            row_index,
            batch.record.record_id,
            _excel_date(batch.record.test_date),
            batch.record.supplier,
            _number(batch.statistics.mean),
            _number(batch.statistics.range_value),
            _number(batch.lower_threshold),
            _number(batch.upper_threshold),
            _number(batch.statistics.standard_deviation),
            _number(batch.statistics.median),
            _number(batch.statistics.first_quartile),
            _number(batch.statistics.third_quartile),
            _number(batch.statistics.interquartile_range),
            _number(batch.statistics.maximum_department_average_difference),
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
    worksheet.set_column(0, 0, 8)
    worksheet.set_column(1, 1, 34)
    worksheet.set_column(2, 2, 12)
    worksheet.set_column(3, 3, 14)
    worksheet.set_column(4, 13, 13)
    if not ordered:
        return
    last_row = len(ordered)
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
    worksheet.insert_chart("P2", average_chart, {"x_scale": 1.35, "y_scale": 1.2})

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
    worksheet.insert_chart("P20", range_chart, {"x_scale": 1.35, "y_scale": 1.2})


def _write_trace(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = (
        "批次编号",
        "来源文件",
        "文件哈希",
        "来源工作表",
        "样本行",
        "总重",
        "样本部门映射",
        "规则版本",
        "规则SHA-256",
        "规则适用范围",
        "规则确认状态",
        "经验引用",
    )
    worksheet = workbook.add_worksheet(SHEET_NAMES[3])
    _write_headers(worksheet, headers, formats["header"])
    for row, batch in enumerate(_ordered_batches(report), start=1):
        values = (
            batch.record.record_id,
            batch.record.source_file.name if batch.record.source_file else None,
            batch.record.source_file_hash,
            batch.record.source_sheet,
            ", ".join(str(sample.source_row) for sample in batch.record.samples),
            _number(batch.record.total_weight_kg),
            _department_map(batch),
            batch.rule_version,
            batch.rule_hash,
            batch.rule_applicable_scope,
            "已确认" if batch.rule_confirmation_status == "confirmed" else "待业务确认",
            "; ".join(f"{item.entry_id} v{item.version}" for item in batch.experience_references),
        )
        for column, value in enumerate(values):
            cell_format = formats["wrap"] if column in {1, 2, 6, 8, 9, 11} else formats["text"]
            if isinstance(value, (int, float)):
                worksheet.write_number(row, column, value, formats["weight"])
            else:
                worksheet.write(row, column, value, cell_format)
        worksheet.set_row(row, 30)
    worksheet.set_column(0, 0, 34)
    worksheet.set_column(1, 1, 32)
    worksheet.set_column(2, 2, 68)
    worksheet.set_column(3, 11, 22)


def _write_model_records(workbook: Any, report: WorkbookReport, formats: dict[str, Any]) -> None:
    headers = (
        "批次编号",
        "初筛状态",
        "AI复判状态",
        "置信度",
        "最终显示色",
        "人工确认状态",
        "AI理由",
        "降级原因",
    )
    worksheet = workbook.add_worksheet(SHEET_NAMES[4])
    _write_headers(worksheet, headers, formats["header"])
    for row, batch in enumerate(_ordered_batches(report), start=1):
        values = (
            batch.record.record_id,
            screen_label(batch.screening_decision.status),
            review_label(batch.ai_review.status),
            _number(batch.ai_review.confidence),
            color_label(batch.final_display_color),
            confirmation_label(batch.confirmation_state),
            batch.ai_review.rationale,
            batch.ai_degradation_reason,
        )
        for column, value in enumerate(values):
            cell_format = formats["number"] if column == 3 else formats["wrap"]
            if value is None:
                worksheet.write_blank(row, column, None, cell_format)
            elif isinstance(value, (int, float)):
                worksheet.write_number(row, column, value, cell_format)
            else:
                worksheet.write(row, column, value, cell_format)
        worksheet.set_row(row, 36)
    worksheet.set_column(0, 0, 34)
    worksheet.set_column(1, 1, 18)
    worksheet.set_column(2, 2, 28)
    worksheet.set_column(3, 5, 18)
    worksheet.set_column(6, 7, 36)


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
