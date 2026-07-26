from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from after_sales_agent.analysis import ISSUE_ORDER, build_analysis_metrics
from after_sales_agent.manual_review import (
    effective_after_sales_fee,
    effective_responsible_factory,
)


def write_summary_workbook(
    records: list[dict[str, Any]], output_path: Path, rules: dict[str, Any]
) -> None:
    wb = Workbook()
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"
    # 每个输入文件必须在总表中保留一行。无法解析的文件排在末尾，并在
    # “分析状态/失败原因/纳入业务汇总”列中明确说明，不允许静默漏掉。
    summary_records = sorted(records, key=_chronological_record_sort_key)
    worksheet = wb.active
    worksheet.title = "售后全量总表"
    _write_master_detail(worksheet, summary_records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def _chronological_record_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    year, month, day = _record_date_parts(record)
    input_index = _safe_int(record.get("input_index"), 0)
    if year is not None and month is not None:
        return (0, year, month, day if day is not None else 32, input_index)
    if month is not None:
        return (1, 9999, month, day if day is not None else 32, input_index)
    return (2, 9999, 99, 32, input_index)


def _record_date_parts(record: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    """Return sortable complaint-date parts without borrowing order/delivery dates."""
    value = str(record.get("complaint_date") or "").strip()
    if value:
        try:
            parsed = date.fromisoformat(value)
            return parsed.year, parsed.month, parsed.day
        except ValueError:
            pass
        month_day = re.search(r"(?<!\d)(\d{1,2})\s*月\s*(\d{1,2})?", value)
        if month_day:
            month = _safe_int(month_day.group(1))
            day = _safe_int(month_day.group(2)) if month_day.group(2) else None
            if month is not None and 1 <= month <= 12:
                return None, month, day if day is not None and 1 <= day <= 31 else None

    year = _safe_int(record.get("year"))
    month = _safe_int(record.get("month"))
    if month is None or not 1 <= month <= 12:
        month = None
    return year, month, None


def _safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value) if value not in {None, ""} else default
    except (TypeError, ValueError):
        return default


def _write_master_detail(ws: Any, records: list[dict[str, Any]]) -> None:
    original_columns = [
        ("source_file", "来源文件"),
        ("sheet", "原工作表"),
        ("customer", "客户/项目"),
        ("location", "地点"),
        ("salesperson", "销售/代表"),
        ("brand", "品牌"),
        ("product", "产品"),
        ("spec", "规格"),
        ("order_no", "订单号"),
        ("delivery_date", "交货日期"),
        ("feedback", "客户反馈内容"),
        ("application", "方案申请明细"),
        ("investigation", "售后负责人调查情况"),
        ("solution", "售后解决方案原文"),
        ("responsibility", "责任落实与处理"),
    ]
    analysis_columns = [
        ("after_sales_analysis", "售后问题分析"),
        ("issue_reason_summary", "产生售后的具体原因"),
        ("issue_types_display", "原因分类（性能/外观/加工）"),
        ("performance_flag", "性能"),
        ("appearance_flag", "外观"),
        ("processing_flag", "加工"),
        ("primary_issue_type", "主要原因"),
        ("complaint_type_reviewed_display", "投诉类型复核状态"),
        ("selected_solution", "最终采用方案"),
        ("after_sales_fee_amount", "售后费用（人工复核口径）"),
        ("after_sales_fee_reviewed_display", "售后费用复核状态"),
        ("responsible_factory", "责任工厂（人工复核口径）"),
        ("responsibility_reviewed_display", "责任工厂复核状态"),
        ("enterprise_cost_amount", "最终售后费用（企业承担）"),
        ("internal_accountability_amount", "内部责任扣款"),
        ("external_borne_amount", "外部承担金额"),
        ("enterprise_cost_status", "最终费用状态"),
        ("enterprise_cost_evidence", "最终费用依据"),
        ("resolution_status", "处理状态"),
        ("resolved_flag", "是否已解决"),
        ("analysis_status", "分析状态"),
        ("analysis_error", "失败原因"),
        ("included_in_summary", "纳入业务汇总"),
    ]
    fixed_columns = [
        ("chronological_index", "时间序号"),
        ("input_index", "原输入序号"),
        ("complaint_date", "提出质量问题/报修日期"),
        ("complaint_date_raw", "日期原文"),
    ]
    columns = [*fixed_columns, *original_columns, *analysis_columns]
    last_col = len(columns)
    last_letter = get_column_letter(last_col)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, "售后原始内容、问题分析与费用汇总明细")
    ws.cell(1, 1).font = Font(name="微软雅黑", size=16, bold=True, color="FFFFFF")
    ws.cell(1, 1).fill = PatternFill("solid", fgColor="176B4D")
    ws.cell(1, 1).alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.cell(
        2,
        1,
        "每份输入文件保留一行；先按完整报修日期排序，再列示缺少年份及日期未知的记录。"
        "左侧保留原表业务内容，右侧追加智能分析、原因分类、处理状态和最终费用。",
    )
    ws.cell(2, 1).font = Font(name="微软雅黑", size=9, color="52645B")
    ws.cell(2, 1).fill = PatternFill("solid", fgColor="EAF4EF")
    ws.cell(2, 1).alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws.row_dimensions[2].height = 30

    for col, (_, title) in enumerate(columns, start=1):
        cell = ws.cell(3, col, title)
        cell.fill = PatternFill("solid", fgColor="254F43" if col <= 19 else "2F6B87")
        cell.font = Font(name="微软雅黑", size=9, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[3].height = 34

    amount_keys = {
        "after_sales_fee_amount",
        "enterprise_cost_amount",
        "internal_accountability_amount",
        "external_borne_amount",
    }
    thin = Side(style="thin", color="D7E2DC")
    for row_index, record in enumerate(records, start=4):
        issue_types = _display_issue_types(record)
        display_values: dict[str, Any] = {
            **record,
            "chronological_index": row_index - 3,
            "source_file": Path(str(record.get("source_file") or "")).name,
            "complaint_date": _complaint_date_cell_value(record),
            "after_sales_analysis": _after_sales_analysis_text(record),
            "issue_types_display": "、".join(issue_types) if issue_types else "其他",
            "performance_flag": "是" if "性能" in issue_types else "否",
            "appearance_flag": "是" if "外观" in issue_types else "否",
            "processing_flag": "是" if "加工" in issue_types else "否",
            "complaint_type_reviewed_display": (
                "已复核" if record.get("complaint_type_reviewed") else "待复核"
            ),
            "selected_solution": record.get("selected_solution") or record.get("solution") or "",
            "after_sales_fee_amount": effective_after_sales_fee(record),
            "after_sales_fee_reviewed_display": (
                "已复核" if record.get("after_sales_fee_reviewed") else "待复核"
            ),
            "responsible_factory": effective_responsible_factory(record) or "未知",
            "responsibility_reviewed_display": (
                "已复核" if record.get("responsibility_reviewed") else "待复核"
            ),
            "enterprise_cost_amount": _record_amount(
                record, "enterprise_cost_amount", "fee_amount", "cost"
            ),
            "enterprise_cost_status": _display_cost_status(
                record.get("enterprise_cost_status", record.get("fee_status"))
            ),
            "resolution_status": record.get("resolution_status")
            or ("已解决" if record.get("closed") else "未解决"),
            "resolved_flag": "是" if record.get("resolution_status") == "已解决" else "否",
            "included_in_summary": "是" if record.get("included_in_summary", True) else "否",
        }
        display_values["resolved_flag"] = (
            "是" if display_values["resolution_status"] == "已解决" else "否"
        )
        for col, (key, _) in enumerate(columns, start=1):
            value = display_values.get(key, "")
            if isinstance(value, (list, dict)):
                value = str(value)
            cell = ws.cell(row_index, col, value)
            cell.font = Font(name="微软雅黑", size=9, color="22332B")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin)
            if key in amount_keys:
                cell.number_format = '#,##0.00;[Red]-#,##0.00;"-"'
                cell.alignment = Alignment(horizontal="right", vertical="top")
            elif key in {
                "chronological_index",
                "input_index",
                "performance_flag",
                "appearance_flag",
                "processing_flag",
                "resolved_flag",
                "included_in_summary",
            }:
                cell.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
            elif key == "complaint_date" and isinstance(value, date):
                cell.number_format = "yyyy-mm-dd"
                cell.alignment = Alignment(horizontal="center", vertical="top")
        if row_index % 2 == 1:
            for col in range(1, last_col + 1):
                ws.cell(row_index, col).fill = PatternFill("solid", fgColor="F6FAF8")
        for flag_col in (23, 24, 25):
            if ws.cell(row_index, flag_col).value == "是":
                ws.cell(row_index, flag_col).fill = PatternFill("solid", fgColor="DCEFE6")
                ws.cell(row_index, flag_col).font = Font(
                    name="微软雅黑", size=9, bold=True, color="176B4D"
                )
        if display_values.get("analysis_status") == "分析失败":
            for col in range(1, last_col + 1):
                ws.cell(row_index, col).fill = PatternFill("solid", fgColor="FFF1F0")
        ws.row_dimensions[row_index].height = _master_detail_row_height(display_values)

    widths = [
        9,
        10,
        18,
        18,
        32,
        15,
        24,
        16,
        14,
        12,
        20,
        16,
        18,
        16,
        38,
        38,
        38,
        38,
        32,
        46,
        40,
        22,
        9,
        9,
        9,
        12,
        36,
        18,
        16,
        16,
        16,
        36,
        12,
        11,
        13,
        32,
        13,
    ]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "E4"
    ws.sheet_view.showGridLines = False
    ws.auto_filter.ref = f"A3:{last_letter}{max(3, len(records) + 3)}"
    ws.print_title_rows = "1:3"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_area = f"A1:{last_letter}{max(3, len(records) + 3)}"


def _complaint_date_cell_value(record: dict[str, Any]) -> date | str:
    value = str(record.get("complaint_date") or "").strip()
    if not value:
        return str(record.get("complaint_date_raw") or "")
    try:
        return date.fromisoformat(value)
    except ValueError:
        return value


def _display_issue_types(record: dict[str, Any]) -> list[str]:
    raw = record.get("issue_types")
    if not isinstance(raw, list):
        raw = [record.get("primary_issue_type")]
    ordered = [item for item in ["性能", "外观", "加工"] if item in raw]
    ordered.extend(str(item) for item in raw if item and str(item) not in ordered)
    return ordered


def _after_sales_analysis_text(record: dict[str, Any]) -> str:
    if record.get("analysis_status") == "分析失败":
        return str(record.get("issue_reason_summary") or record.get("analysis_error") or "")
    sections: list[str] = []
    feedback = str(record.get("feedback") or "").strip()
    investigation = str(record.get("investigation") or "").strip()
    conclusion = str(record.get("issue_reason_summary") or "").strip()
    if feedback:
        sections.append(f"问题表现：{feedback}")
    if investigation:
        sections.append(f"调查情况：{investigation}")
    if conclusion:
        sections.append(f"分析结论：{conclusion}")
    return "\n".join(dict.fromkeys(sections)) or "未提取到可确认的问题描述"


def _display_cost_status(value: Any) -> str:
    statuses = {
        "exact": "已确认",
        "calculated": "已计算",
        "estimated": "估算待复核",
        "transferred": "外部承担",
        "not_found": "未识别",
        "needs_review": "待复核",
    }
    text = str(value or "").strip()
    return statuses.get(text, text)


def _master_detail_row_height(values: dict[str, Any]) -> float:
    narrative_keys = [
        "feedback",
        "application",
        "investigation",
        "solution",
        "responsibility",
        "after_sales_analysis",
        "issue_reason_summary",
        "selected_solution",
        "enterprise_cost_evidence",
    ]
    estimated_lines = 1
    for key in narrative_keys:
        text = str(values.get(key) or "")
        logical_lines = sum(max(1, (len(line) + 54) // 55) for line in text.splitlines())
        estimated_lines = max(estimated_lines, logical_lines)
    return min(240.0, max(72.0, 13.5 * (estimated_lines + 1)))


def _ordered_brands(records: list[dict[str, Any]], rules: dict[str, Any]) -> list[str]:
    discovered: list[str] = []
    for record in records:
        brand = str(record.get("brand") or "未知").strip() or "未知"
        if brand not in discovered:
            discovered.append(brand)
    configured = [str(item) for item in rules.get("brand_order", [])]
    brands = [brand for brand in configured if brand in discovered]
    brands.extend(brand for brand in discovered if brand not in brands)
    return brands or ["未知"]


def _write_chronological_summary(
    ws: Any, records: list[dict[str, Any]], rules: dict[str, Any]
) -> None:
    brands = _ordered_brands(records, rules)
    issue_types = [
        item for item in ["性能", "外观", "加工"] if item in rules.get("issue_order", [])
    ]
    known_periods = sorted(
        {
            (int(record["year"]), int(record["month"]))
            for record in records
            if record.get("year") is not None and record.get("month")
        }
    )
    unknown_periods = [
        (None, month)
        for month in sorted(
            {
                int(record["month"])
                for record in records
                if record.get("year") is None and record.get("month")
            }
        )
    ]
    periods = [*known_periods, *unknown_periods]
    if not periods:
        periods = [(None, month) for month in range(1, 13)]
    period_end_col = 3 + len(periods)
    last_col = period_end_col + 1

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, "全部输入文件售后统计表（按报修年份和月份排序）")
    ws.cell(1, 1).font = Font(name="宋体", size=16, bold=True)
    ws.cell(1, 1).alignment = Alignment(horizontal="center", vertical="center")

    for idx, value in enumerate(["序号", "品牌", "类型"], start=1):
        ws.cell(2, idx, value)
        ws.merge_cells(start_row=2, start_column=idx, end_row=3, end_column=idx)
    group_start = 4
    current_year = periods[0][0]
    for offset, period in enumerate(periods, start=4):
        year, month = period
        ws.cell(3, offset, f"{month}月")
        if year != current_year:
            ws.merge_cells(start_row=2, start_column=group_start, end_row=2, end_column=offset - 1)
            ws.cell(
                2, group_start, f"{current_year}年" if current_year is not None else "年份未注明"
            )
            group_start = offset
            current_year = year
    ws.merge_cells(start_row=2, start_column=group_start, end_row=2, end_column=period_end_col)
    ws.cell(2, group_start, f"{current_year}年" if current_year is not None else "年份未注明")
    ws.cell(2, last_col, "合计")
    ws.merge_cells(start_row=2, start_column=last_col, end_row=3, end_column=last_col)

    counts: dict[tuple[str, str, tuple[int | None, int]], int] = defaultdict(int)
    enterprise_costs: dict[tuple[str, tuple[int | None, int]], float] = defaultdict(float)
    internal_amounts: dict[tuple[str, tuple[int | None, int]], float] = defaultdict(float)
    external_amounts: dict[tuple[str, tuple[int | None, int]], float] = defaultdict(float)
    case_counts: dict[tuple[int | None, int], int] = defaultdict(int)
    closed: dict[tuple[int | None, int], int] = defaultdict(int)
    processing: dict[tuple[int | None, int], int] = defaultdict(int)
    unresolved: dict[tuple[int | None, int], int] = defaultdict(int)
    unknown_fee_count = 0
    for record in records:
        month = record.get("month")
        if not month:
            continue
        year = int(record["year"]) if record.get("year") is not None else None
        period = (year, int(month))
        brand = str(record.get("brand") or "未知").strip() or "未知"
        case_counts[period] += 1
        for issue_type in _record_issue_types(record, issue_types):
            counts[(brand, issue_type, period)] += 1
        amount = _record_amount(record, "enterprise_cost_amount", "fee_amount", "cost")
        if amount is None:
            unknown_fee_count += 1
        else:
            enterprise_costs[(brand, period)] += amount
        internal = _record_amount(record, "internal_accountability_amount")
        if internal is not None:
            internal_amounts[(brand, period)] += internal
        external = _record_amount(record, "external_borne_amount")
        if external is not None:
            external_amounts[(brand, period)] += external
        status = record.get("resolution_status") or ("已解决" if record.get("closed") else "未解决")
        if status == "已解决":
            closed[period] += 1
        elif status == "处理中":
            processing[period] += 1
        else:
            unresolved[period] += 1

    row = 4
    serial = 1
    case_rows: list[int] = []
    enterprise_rows: list[int] = []
    internal_rows: list[int] = []
    external_rows: list[int] = []
    fee_fill = PatternFill("solid", fgColor="FFFF00")
    for brand in brands:
        brand_start = row
        for issue_type in issue_types:
            case_rows.append(row)
            ws.cell(row, 1, serial)
            ws.cell(row, 2, brand)
            ws.cell(row, 3, issue_type)
            serial += 1
            for col, period in enumerate(periods, start=4):
                ws.cell(row, col, counts[(brand, issue_type, period)])
            ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
            row += 1
        for label, values, target_rows in [
            ("企业售后成本", enterprise_costs, enterprise_rows),
            ("内部责任扣款", internal_amounts, internal_rows),
            ("外部承担金额", external_amounts, external_rows),
        ]:
            target_rows.append(row)
            ws.cell(row, 1, serial)
            ws.cell(row, 2, brand)
            ws.cell(row, 3, label)
            serial += 1
            for col, period in enumerate(periods, start=4):
                ws.cell(row, col, round(values[(brand, period)], 2))
                ws.cell(row, col).fill = fee_fill
            ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
            for col in range(1, last_col + 1):
                ws.cell(row, col).fill = fee_fill
            for col in range(4, last_col + 1):
                ws.cell(row, col).number_format = "0.00"
            row += 1
        if row > brand_start:
            ws.merge_cells(start_row=brand_start, start_column=2, end_row=row - 1, end_column=2)

    subtotal_row = row
    summary_rows = [
        ("分类标签合计", case_rows, None),
        ("企业售后成本", enterprise_rows, "0.00"),
        ("内部责任扣款", internal_rows, "0.00"),
        ("外部承担金额", external_rows, "0.00"),
    ]
    for label, source_rows, number_format in summary_rows:
        ws.cell(row, 2, label)
        for col in range(4, period_end_col + 1):
            letter = get_column_letter(col)
            ws.cell(
                row, col, f"=SUM({','.join(f'{letter}{source_row}' for source_row in source_rows)})"
            )
            if number_format:
                ws.cell(row, col).number_format = number_format
        ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
        if number_format:
            ws.cell(row, last_col).number_format = number_format
        row += 1
    ws.cell(row, 2, "案件总数（每案计1次）")
    for col, period in enumerate(periods, start=4):
        ws.cell(row, col, case_counts[period])
    ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
    row += 1
    for label, values in [
        ("关闭数", closed),
        ("处理中数量", processing),
        ("未解决数量", unresolved),
    ]:
        ws.cell(row, 2, label)
        for col, period in enumerate(periods, start=4):
            ws.cell(row, col, values[period])
        ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
        row += 1
    summary_end_row = row - 1
    ws.cell(row, 1, "备注：")
    row += 1
    for note in [
        "1、各列先按年份、再按月份排列；年份未注明的数据单独列示，不与已知年份同月相加。",
        "2、问题分类为多标签统计，同一案件可进入多个分类；分类标签合计不能作为案件总数。",
        "3、企业售后成本、内部责任扣款和外部承担金额分别统计，后两者不计入企业售后成本。",
        f"4、未知企业售后成本不计入金额合计；本页共有 {unknown_fee_count} 条企业成本为空或待确认。",
    ]:
        ws.cell(row, 1, note)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
        row += 1
    _style_summary(ws, last_col, subtotal_row, summary_end_row)


def _write_input_audit(ws: Any, records: list[dict[str, Any]]) -> None:
    columns = [
        ("input_index", "输入序号"),
        ("source_file", "输入文件"),
        ("analysis_status", "分析状态"),
        ("analysis_error", "失败原因"),
        ("included_in_summary", "纳入汇总"),
        ("brand", "品牌"),
        ("complaint_date_raw", "提出质量问题/报修日期（原值）"),
        ("complaint_date", "规范日期"),
        ("year", "年份"),
        ("month", "月份"),
        ("primary_issue_type", "主要原因"),
        ("issue_reason_summary", "产生售后的具体原因"),
        ("complaint_type_reviewed", "投诉类型已复核"),
        ("after_sales_fee_amount", "售后费用"),
        ("after_sales_fee_status", "售后费用复核状态"),
        ("after_sales_fee_reviewed", "售后费用已复核"),
        ("responsible_factory", "责任工厂"),
        ("responsibility_reviewed", "责任工厂已复核"),
        ("manual_review_completed", "三项人工复核完成"),
        ("enterprise_cost_amount", "企业售后成本"),
        ("enterprise_cost_status", "企业成本状态"),
        ("enterprise_cost_evidence", "企业成本依据"),
        ("internal_accountability_amount", "内部责任扣款"),
        ("internal_accountability_status", "内部扣款状态"),
        ("internal_accountability_evidence", "内部扣款依据"),
        ("external_borne_amount", "外部承担金额"),
        ("external_borne_status", "外部承担状态"),
        ("external_borne_evidence", "外部承担依据"),
        ("resolution_status", "处理状态"),
        ("resolution_reason", "状态依据"),
    ]
    for col, (_, title) in enumerate(columns, start=1):
        ws.cell(1, col, title)
    for row_idx, record in enumerate(records, start=2):
        for col, (key, _) in enumerate(columns, start=1):
            value = record.get(key, "")
            if key == "source_file":
                value = Path(str(value)).name
            elif key == "included_in_summary":
                value = "是" if value else "否"
            elif key == "analysis_status" and value == "AI分析完成":
                value = "智能分析完成"
            ws.cell(row_idx, col, value)

    header_fill = PatternFill("solid", fgColor="176B4D")
    thin = Side(style="thin", color="D7E2DC")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.border = Border(bottom=thin)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.font = Font(name="微软雅黑", size=9)
    ws.freeze_panes = "C2"
    widths = [
        9,
        34,
        12,
        28,
        11,
        12,
        24,
        16,
        9,
        8,
        11,
        42,
        15,
        18,
        36,
        15,
        18,
        36,
        15,
        18,
        36,
        12,
        36,
    ]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    for row_idx in range(2, len(records) + 2):
        ws.row_dimensions[row_idx].height = 42
    for col, (key, _) in enumerate(columns, start=1):
        if key.endswith("_amount"):
            for cell in ws[get_column_letter(col)][1:]:
                cell.number_format = "#,##0.00"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(1, len(records) + 1)}"


def _write_year_summary(
    ws: Any,
    year: int | None,
    records: list[dict[str, Any]],
    rules: dict[str, Any],
    title: str | None = None,
) -> None:
    discovered_brands: list[str] = []
    for record in records:
        brand = str(record.get("brand") or "未知").strip() or "未知"
        if brand not in discovered_brands:
            discovered_brands.append(brand)
    configured_order = [str(item) for item in rules.get("brand_order", [])]
    brands = [brand for brand in configured_order if brand in discovered_brands]
    brands.extend(brand for brand in discovered_brands if brand not in brands)
    if not brands:
        brands = ["未知"]
    issue_types = [
        item for item in ["性能", "外观", "加工"] if item in rules.get("issue_order", [])
    ]
    months = list(range(1, 13))
    last_col = 4 + len(months)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.cell(1, 1, title or (f"{year}年售后统计表" if year else "全部输入文件售后统计表"))
    ws.cell(1, 1).font = Font(name="宋体", size=16, bold=True)
    ws.cell(1, 1).alignment = Alignment(horizontal="center", vertical="center")

    headers = ["序号", "品牌", "类型"]
    for idx, value in enumerate(headers, start=1):
        ws.cell(2, idx, value)
        ws.merge_cells(start_row=2, start_column=idx, end_row=3, end_column=idx)
    ws.merge_cells(start_row=2, start_column=4, end_row=2, end_column=3 + len(months))
    ws.cell(2, 4, "月份")
    ws.cell(2, last_col, "合计")
    ws.merge_cells(start_row=2, start_column=last_col, end_row=3, end_column=last_col)
    for offset, month in enumerate(months, start=4):
        ws.cell(3, offset, month)

    counts: dict[tuple[str, str, int], int] = defaultdict(int)
    enterprise_costs: dict[tuple[str, int], float] = defaultdict(float)
    internal_amounts: dict[tuple[str, int], float] = defaultdict(float)
    external_amounts: dict[tuple[str, int], float] = defaultdict(float)
    case_totals_by_month: dict[int, int] = defaultdict(int)
    closed_by_month: dict[int, int] = defaultdict(int)
    processing_by_month: dict[int, int] = defaultdict(int)
    unresolved_by_month: dict[int, int] = defaultdict(int)
    unknown_fee_count = 0

    for record in records:
        brand = record.get("brand") or "未知"
        month = record.get("month")
        if not month:
            continue
        if brand not in brands:
            brands.append(brand)
        for issue_type in _record_issue_types(record, issue_types):
            counts[(brand, issue_type, month)] += 1
        case_totals_by_month[month] += 1
        fee_amount = _record_amount(record, "enterprise_cost_amount", "fee_amount", "cost")
        if fee_amount is None:
            unknown_fee_count += 1
        else:
            enterprise_costs[(brand, month)] += fee_amount
        internal = _record_amount(record, "internal_accountability_amount")
        if internal is not None:
            internal_amounts[(brand, month)] += internal
        external = _record_amount(record, "external_borne_amount")
        if external is not None:
            external_amounts[(brand, month)] += external
        resolution_status = record.get("resolution_status") or (
            "已解决" if record.get("closed") else "未解决"
        )
        if resolution_status == "已解决":
            closed_by_month[month] += 1
        elif resolution_status == "处理中":
            processing_by_month[month] += 1
        else:
            unresolved_by_month[month] += 1

    row = 4
    serial = 1
    case_rows: list[int] = []
    enterprise_rows: list[int] = []
    internal_rows: list[int] = []
    external_rows: list[int] = []
    fee_fill = PatternFill("solid", fgColor="FFFF00")
    for brand in brands:
        brand_start = row
        for issue_type in issue_types:
            case_rows.append(row)
            ws.cell(row, 1, serial)
            ws.cell(row, 2, brand)
            ws.cell(row, 3, issue_type)
            serial += 1
            total = 0
            for col, month in enumerate(months, start=4):
                value = counts[(brand, issue_type, month)]
                total += value
                ws.cell(row, col, value)
            ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
            row += 1
        for label, values, target_rows in [
            ("企业售后成本", enterprise_costs, enterprise_rows),
            ("内部责任扣款", internal_amounts, internal_rows),
            ("外部承担金额", external_amounts, external_rows),
        ]:
            target_rows.append(row)
            ws.cell(row, 1, serial)
            ws.cell(row, 2, brand)
            ws.cell(row, 3, label)
            serial += 1
            for col, month in enumerate(months, start=4):
                ws.cell(row, col, round(values[(brand, month)], 2))
                ws.cell(row, col).fill = fee_fill
            ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
            for col in range(1, last_col + 1):
                ws.cell(row, col).fill = fee_fill
            for col in range(4, last_col + 1):
                ws.cell(row, col).number_format = "0.00"
            row += 1
        if row > brand_start:
            ws.merge_cells(start_row=brand_start, start_column=2, end_row=row - 1, end_column=2)

    subtotal_row = row
    ws.cell(row, 2, "分类标签合计")
    for col, _month in enumerate(months, start=4):
        column = get_column_letter(col)
        ws.cell(row, col, f"=SUM({','.join(f'{column}{source_row}' for source_row in case_rows)})")
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    row += 1
    for label, source_rows in [
        ("企业售后成本", enterprise_rows),
        ("内部责任扣款", internal_rows),
        ("外部承担金额", external_rows),
    ]:
        ws.cell(row, 2, label)
        for col, _month in enumerate(months, start=4):
            column = get_column_letter(col)
            ws.cell(
                row, col, f"=SUM({','.join(f'{column}{source_row}' for source_row in source_rows)})"
            )
        ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
        for col in range(4, last_col + 1):
            ws.cell(row, col).number_format = "0.00"
        row += 1
    ws.cell(row, 2, "案件总数（每案计1次）")
    for col, month in enumerate(months, start=4):
        ws.cell(row, col, case_totals_by_month[month])
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    row += 1
    ws.cell(row, 2, "关闭数")
    for col, month in enumerate(months, start=4):
        ws.cell(row, col, closed_by_month[month])
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    row += 1
    ws.cell(row, 2, "处理中数量")
    for col, month in enumerate(months, start=4):
        ws.cell(row, col, processing_by_month[month])
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    row += 1
    ws.cell(row, 2, "未解决数量")
    for col, month in enumerate(months, start=4):
        ws.cell(row, col, unresolved_by_month[month])
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    summary_end_row = row
    row += 1

    ws.cell(row, 1, "备注：")
    row += 1
    ws.cell(
        row, 1, "1、问题分类为多标签统计，同一案件可进入多个分类，分类数量不能相加作为案件总数。"
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    row += 1
    ws.cell(
        row, 1, "2、企业售后成本、内部责任扣款和外部承担金额分别统计，后两者不计入企业售后成本。"
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    row += 1
    ws.cell(
        row,
        1,
        f"3、未知企业售后成本不计入金额合计；本页共有 {unknown_fee_count} 条企业成本为空或待确认。",
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)

    _style_summary(ws, last_col, subtotal_row, summary_end_row)


def _write_detail(ws: Any, records: list[dict[str, Any]]) -> None:
    columns = [
        ("input_index", "输入序号"),
        ("source_file", "来源文件"),
        ("analysis_status", "分析状态"),
        ("analysis_error", "失败原因"),
        ("included_in_summary", "纳入业务汇总"),
        ("sheet", "工作表"),
        ("customer", "客户/项目"),
        ("location", "地点"),
        ("salesperson", "销售/代表"),
        ("brand", "品牌"),
        ("product", "产品"),
        ("spec", "规格"),
        ("order_no", "订单"),
        ("complaint_date_raw", "提出质量问题/报修日期（原值）"),
        ("complaint_date", "规范日期"),
        ("year", "年份"),
        ("month", "月份"),
        ("date_analysis_source", "日期来源"),
        ("brand_reason", "品牌判断依据"),
        ("issue_types", "问题类型"),
        ("primary_issue_type", "主要类型"),
        ("issue_analysis_source", "分类来源"),
        ("issue_confidence", "分类置信度"),
        ("issue_reason_summary", "产生售后的具体原因"),
        ("complaint_type_reviewed", "投诉类型已复核"),
        ("after_sales_fee_amount", "售后费用"),
        ("after_sales_fee_status", "售后费用复核状态"),
        ("after_sales_fee_reviewed", "售后费用已复核"),
        ("responsible_factory", "责任工厂"),
        ("responsibility_reviewed", "责任工厂已复核"),
        ("manual_review_completed", "三项人工复核完成"),
        ("enterprise_cost_amount", "企业售后成本"),
        ("enterprise_cost_status", "企业成本状态"),
        ("enterprise_cost_evidence", "企业成本依据"),
        ("enterprise_cost_reviewed", "企业成本已复核"),
        ("internal_accountability_amount", "内部责任扣款"),
        ("internal_accountability_status", "内部扣款状态"),
        ("internal_accountability_evidence", "内部扣款依据"),
        ("internal_accountability_reviewed", "内部扣款已复核"),
        ("external_borne_amount", "外部承担金额"),
        ("external_borne_status", "外部承担状态"),
        ("external_borne_evidence", "外部承担依据"),
        ("external_borne_reviewed", "外部承担已复核"),
        ("fee_amount", "企业售后成本（兼容字段）"),
        ("fee_currency", "币种"),
        ("fee_status", "费用状态"),
        ("cost_included", "纳入费用统计"),
        ("cost_status", "费用识别状态"),
        ("cost_items", "费用明细"),
        ("cost_analysis_source", "费用来源"),
        ("resolution_status", "处理状态"),
        ("case_status", "案件状态"),
        ("resolution_analysis_source", "状态来源"),
        ("resolution_reason", "状态依据"),
        ("brand_confidence", "品牌置信度"),
        ("warnings", "警告"),
        ("source_cells", "来源单元格"),
        ("reviewed", "是否人工复核"),
        ("reviewed_by", "复核人"),
        ("reviewed_at", "修改时间"),
        ("brand_evidence", "品牌证据"),
        ("issue_evidence", "问题证据"),
        ("api_analysis", "API分析原文"),
        ("cost_evidence", "费用证据"),
        ("feedback", "客户反馈原文"),
        ("investigation", "售后调查原文"),
        ("application", "方案申请原文"),
        ("solution", "售后解决方案"),
        ("responsibility", "责任落实原文"),
    ]
    for col, (_, title) in enumerate(columns, start=1):
        ws.cell(1, col, title)
    for row_idx, record in enumerate(records, start=2):
        for col, (key, _) in enumerate(columns, start=1):
            value = record.get(key, "")
            if key == "source_file":
                value = Path(str(value)).name
            if key == "analysis_status" and value == "AI分析完成":
                value = "智能分析完成"
            if isinstance(value, (list, dict)):
                value = str(value)
            ws.cell(row_idx, col, value)
    ws.freeze_panes = "A2"
    for col in range(1, len(columns) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 18
    ws.column_dimensions["B"].width = 46
    ws.column_dimensions["D"].width = 42
    ws.column_dimensions["W"].width = 42
    ws.column_dimensions["Y"].width = 48


def _write_review(ws: Any, records: list[dict[str, Any]]) -> None:
    review_records = [
        record
        for record in records
        if record.get("needs_review")
        or record.get("mandatory_review_pending")
        or record.get("manual_review_completed")
        or record.get("brand") in {"未知", "待确认"}
        or record.get("primary_issue_type") in {"其他", "待确认", None, ""}
        or record.get("enterprise_cost_status", record.get("fee_status"))
        in {"not_found", "needs_review"}
        or record.get("internal_accountability_status") == "needs_review"
        or record.get("external_borne_status") == "needs_review"
        or record.get("warnings")
    ]
    columns = [
        ("input_index", "输入序号"),
        ("source_file", "来源文件"),
        ("brand", "品牌"),
        ("complaint_date", "提出质量问题/报修日期"),
        ("primary_issue_type", "主原因"),
        ("complaint_type_reviewed", "投诉类型已复核"),
        ("after_sales_fee_amount", "售后费用"),
        ("after_sales_fee_status", "售后费用状态"),
        ("after_sales_fee_reviewed", "售后费用已复核"),
        ("responsible_factory", "责任工厂"),
        ("responsibility_reviewed", "责任工厂已复核"),
        ("manual_review_completed", "三项复核完成"),
        ("enterprise_cost_amount", "企业售后成本"),
        ("enterprise_cost_status", "企业成本状态"),
        ("internal_accountability_amount", "内部责任扣款"),
        ("internal_accountability_status", "内部扣款状态"),
        ("external_borne_amount", "外部承担金额"),
        ("external_borne_status", "外部承担状态"),
        ("case_status", "案件状态"),
        ("warnings", "警告"),
        ("issue_reason_summary", "原因与现象"),
        ("cost_evidence", "费用证据"),
        ("brand_evidence", "品牌证据"),
        ("source_cells", "来源单元格"),
        ("reviewed", "是否已复核"),
    ]
    for col, (_, title) in enumerate(columns, start=1):
        ws.cell(1, col, title)
    for row_index, record in enumerate(review_records, start=2):
        for col, (key, _) in enumerate(columns, start=1):
            value = record.get(key, "")
            if key == "source_file":
                value = Path(str(value)).name
            if isinstance(value, (list, dict)):
                value = str(value)
            if key in {
                "reviewed",
                "complaint_type_reviewed",
                "after_sales_fee_reviewed",
                "responsibility_reviewed",
                "manual_review_completed",
            }:
                value = "是" if value else "否"
            ws.cell(row_index, col, value)
    header_fill = PatternFill("solid", fgColor="334E68")
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.font = Font(name="微软雅黑", size=9)
    widths = [
        9,
        36,
        12,
        20,
        12,
        14,
        14,
        18,
        14,
        14,
        14,
        14,
        15,
        18,
        15,
        18,
        15,
        18,
        12,
        42,
        46,
        44,
        32,
        30,
        12,
    ]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{max(1, len(review_records) + 1)}"


def _write_analysis_charts(ws: Any, records: list[dict[str, Any]]) -> None:
    metrics = build_analysis_metrics(records)
    ws.merge_cells("A1:E1")
    ws["A1"] = "售后趋势与结构分析"
    ws["A1"].font = Font(name="微软雅黑", size=16, bold=True, color="176B4D")
    ws["A2"] = "分类采用多标签统计；企业售后成本、内部责任扣款和外部承担金额分别计算。"
    ws.merge_cells("A2:E2")
    ws["A2"].alignment = Alignment(wrap_text=True)
    if not metrics["case_count"]:
        ws["A4"] = "本次没有成功处理的有效案件，未生成空白图表。"
        ws.column_dimensions["A"].width = 62
        return

    monthly = metrics["monthly"]
    monthly_headers = [
        "报修月份",
        "案件数",
        "企业售后成本（元）",
        "内部责任扣款（元）",
        "外部承担金额（元）",
    ]
    for col, value in enumerate(monthly_headers, start=1):
        ws.cell(4, col, value)
    for row, item in enumerate(monthly, start=5):
        ws.cell(row, 1, item["period"])
        ws.cell(row, 2, item["case_count"])
        ws.cell(row, 3, item["enterprise_cost_amount"])
        ws.cell(row, 4, item["internal_accountability_amount"])
        ws.cell(row, 5, item["external_borne_amount"])
        for col in range(3, 6):
            ws.cell(row, col).number_format = "#,##0.00"

    issue_start = max(8, len(monthly) + 7)
    ws.cell(issue_start, 1, "问题类型")
    ws.cell(issue_start, 2, "标签数量")
    for offset, issue in enumerate(ISSUE_ORDER, start=1):
        ws.cell(issue_start + offset, 1, issue)
        ws.cell(issue_start + offset, 2, metrics["issue_counts"][issue])

    line = LineChart()
    line.title = "月度售后案件数量趋势"
    line.y_axis.title = "案件数（件）"
    line.x_axis.title = "提出质量问题/报修月份"
    line.legend = None
    line.y_axis.scaling.min = 0
    line.y_axis.scaling.max = max(2, max(item["case_count"] for item in monthly))
    line.y_axis.majorUnit = 1
    line.y_axis.numFmt = "0"
    line.add_data(
        Reference(ws, min_col=2, min_row=4, max_row=4 + len(monthly)), titles_from_data=True
    )
    line.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + len(monthly)))
    line.height = 7.5
    line.width = 14
    ws.add_chart(line, "G2")

    issue_chart = BarChart()
    issue_chart.type = "col"
    issue_chart.title = "售后问题类型分布（多标签）"
    issue_chart.y_axis.title = "标签数量（条）"
    issue_chart.x_axis.title = "问题类型"
    issue_chart.legend = None
    issue_chart.y_axis.scaling.min = 0
    issue_chart.y_axis.scaling.max = max(2, max(metrics["issue_counts"].values()) + 1)
    issue_chart.y_axis.majorUnit = 1
    issue_chart.y_axis.numFmt = "0"
    issue_chart.add_data(
        Reference(ws, min_col=2, min_row=issue_start, max_row=issue_start + len(ISSUE_ORDER)),
        titles_from_data=True,
    )
    issue_chart.set_categories(
        Reference(ws, min_col=1, min_row=issue_start + 1, max_row=issue_start + len(ISSUE_ORDER))
    )
    issue_chart.height = 7.5
    issue_chart.width = 14
    ws.add_chart(issue_chart, "G18")

    cost_chart = LineChart()
    cost_chart.title = "企业售后成本趋势"
    cost_chart.y_axis.title = "企业售后成本（元）"
    cost_chart.x_axis.title = "提出质量问题/报修月份"
    cost_chart.legend = None
    cost_chart.y_axis.scaling.min = 0
    cost_chart.y_axis.numFmt = "#,##0.00"
    cost_chart.add_data(
        Reference(ws, min_col=3, min_row=4, max_row=4 + len(monthly)), titles_from_data=True
    )
    cost_chart.set_categories(Reference(ws, min_col=1, min_row=5, max_row=4 + len(monthly)))
    cost_chart.height = 7.5
    cost_chart.width = 14
    ws.add_chart(cost_chart, "G34")

    header_fill = PatternFill("solid", fgColor="DCEFE6")
    for row in (4, issue_start):
        for cell in ws[row][:5]:
            cell.fill = header_fill
            cell.font = Font(name="微软雅黑", bold=True, color="174A36")
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for col, width in enumerate([22, 13, 22, 22, 22], start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "A4"


def _record_issue_types(record: dict[str, Any], allowed: list[str]) -> set[str]:
    raw = record.get("issue_types")
    if not isinstance(raw, list) or not raw:
        raw = [record.get("primary_issue_type")]
    return {str(item) for item in raw if str(item) in allowed}


def _record_amount(record: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = record.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _style_summary(ws: Any, last_col: int, subtotal_row: int, summary_end_row: int) -> None:
    thin = Side(style="thin", color="000000")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border
            cell.font = Font(name="宋体", size=10)
    ws.cell(1, 1).font = Font(name="宋体", size=16, bold=True)
    for row_idx in [2, 3, *range(subtotal_row, summary_end_row + 1)]:
        for col in range(1, last_col + 1):
            ws.cell(row_idx, col).font = Font(name="宋体", size=10, bold=True)
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 12
    for col in range(4, last_col + 1):
        ws.column_dimensions[get_column_letter(col)].width = 11
    ws.row_dimensions[1].height = 28
