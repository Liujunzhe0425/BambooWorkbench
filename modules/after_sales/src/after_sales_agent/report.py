from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from after_sales_agent.analysis import ISSUE_ORDER, build_analysis_metrics


def write_summary_workbook(
    records: list[dict[str, Any]], output_path: Path, rules: dict[str, Any]
) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = "auto"
    summary_records = [record for record in records if record.get("included_in_summary", True)]
    years = sorted({record.get("year") for record in summary_records if record.get("year")})
    if not years:
        years = [None]
    chronological_records = sorted(records, key=_chronological_record_sort_key)
    chronological_summary_records = [
        record for record in chronological_records if record.get("included_in_summary", True)
    ]
    # 第一张表按“年份 -> 月份”连续排列，年份不明的数据单独列示，绝不把不同年份的同月混算。
    all_ws = wb.create_sheet("全部统计")
    _write_chronological_summary(all_ws, chronological_summary_records, rules)
    for year in years:
        if year is None:
            continue
        year_records = (
            [r for r in summary_records if r.get("year") == year] if year else summary_records
        )
        ws = wb.create_sheet(f"{year}统计" if year else "售后统计")
        _write_year_summary(ws, year, year_records, rules)
    unknown_year_records = [r for r in summary_records if r.get("year") is None]
    if unknown_year_records:
        ws = wb.create_sheet("年份未注明")
        _write_year_summary(ws, None, unknown_year_records, rules, title="未注明年份售后统计表")
    audit = wb.create_sheet("输入文件对账")
    _write_input_audit(audit, chronological_records)
    detail = wb.create_sheet("售后明细")
    _write_detail(detail, chronological_records)
    review = wb.create_sheet("待人工确认")
    _write_review(review, chronological_records)
    charts = wb.create_sheet("分析图表", 1)
    _write_analysis_charts(charts, chronological_summary_records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)


def _chronological_record_sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    year = record.get("year")
    month = record.get("month")
    try:
        year_value = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_value = None
    try:
        month_value = int(month) if month is not None else 99
    except (TypeError, ValueError):
        month_value = 99
    return (
        0 if year_value is not None else 1,
        year_value if year_value is not None else 9999,
        month_value,
        str(record.get("complaint_date") or ""),
        int(record.get("input_index") or 0),
    )


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
            if key == "reviewed":
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
    widths = [9, 36, 12, 20, 12, 15, 18, 15, 18, 15, 18, 12, 42, 46, 44, 32, 30, 12]
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
