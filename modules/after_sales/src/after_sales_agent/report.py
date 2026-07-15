from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def write_summary_workbook(records: list[dict[str, Any]], output_path: Path, rules: dict[str, Any]) -> None:
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
    chronological_summary_records = [record for record in chronological_records if record.get("included_in_summary", True)]
    # 第一张表按“年份 -> 月份”连续排列，年份不明的数据单独列示，绝不把不同年份的同月混算。
    all_ws = wb.create_sheet("全部统计")
    _write_chronological_summary(all_ws, chronological_summary_records, rules)
    for year in years:
        if year is None:
            continue
        year_records = [r for r in summary_records if r.get("year") == year] if year else summary_records
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


def _write_chronological_summary(ws: Any, records: list[dict[str, Any]], rules: dict[str, Any]) -> None:
    brands = _ordered_brands(records, rules)
    issue_types = [item for item in ["性能", "外观", "加工"] if item in rules.get("issue_order", [])]
    known_periods = sorted({
        (int(record["year"]), int(record["month"]))
        for record in records
        if record.get("year") is not None and record.get("month")
    })
    unknown_periods = [(None, month) for month in sorted({
        int(record["month"])
        for record in records
        if record.get("year") is None and record.get("month")
    })]
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
            ws.cell(2, group_start, f"{current_year}年" if current_year is not None else "年份未注明")
            group_start = offset
            current_year = year
    ws.merge_cells(start_row=2, start_column=group_start, end_row=2, end_column=period_end_col)
    ws.cell(2, group_start, f"{current_year}年" if current_year is not None else "年份未注明")
    ws.cell(2, last_col, "合计")
    ws.merge_cells(start_row=2, start_column=last_col, end_row=3, end_column=last_col)

    counts: dict[tuple[str, str, tuple[int | None, int]], int] = defaultdict(int)
    costs: dict[tuple[str, tuple[int | None, int]], float] = defaultdict(float)
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
        issue_type = record.get("primary_issue_type") or "其他"
        if issue_type not in issue_types:
            issue_type = "其他"
        counts[(brand, issue_type, period)] += 1
        amount = record.get("fee_amount", record.get("cost"))
        if amount is None:
            unknown_fee_count += 1
        elif record.get("cost_included", True):
            costs[(brand, period)] += float(amount)
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
    fee_rows: list[int] = []
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
        fee_rows.append(row)
        ws.cell(row, 1, serial)
        ws.cell(row, 2, brand)
        ws.cell(row, 3, "费用")
        serial += 1
        for col, period in enumerate(periods, start=4):
            ws.cell(row, col, round(costs[(brand, period)], 2))
            ws.cell(row, col).fill = fee_fill
        ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
        for col in range(1, last_col + 1):
            ws.cell(row, col).fill = fee_fill
        for col in range(4, last_col + 1):
            ws.cell(row, col).number_format = "0.00"
        if row > brand_start:
            ws.merge_cells(start_row=brand_start, start_column=2, end_row=row, end_column=2)
        row += 1

    subtotal_row = row
    summary_rows = [
        ("售后小计", case_rows, None),
        ("售后费用", fee_rows, "0.00"),
    ]
    for label, source_rows, number_format in summary_rows:
        ws.cell(row, 2, label)
        for col in range(4, period_end_col + 1):
            letter = get_column_letter(col)
            ws.cell(row, col, f"=SUM({','.join(f'{letter}{source_row}' for source_row in source_rows)})")
            if number_format:
                ws.cell(row, col).number_format = number_format
        ws.cell(row, last_col, f"=SUM(D{row}:{get_column_letter(period_end_col)}{row})")
        if number_format:
            ws.cell(row, last_col).number_format = number_format
        row += 1
    for label, values in [("关闭数", closed), ("处理中数量", processing), ("未解决数量", unresolved)]:
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
        "2、转嫁给合作方或供应商的售后费用不在统计之列。",
        f"3、未知费用不计入金额合计；本页共有 {unknown_fee_count} 条费用为空或待确认。",
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
        ("cost", "费用"),
        ("cost_status", "费用识别状态"),
        ("cost_evidence", "费用依据"),
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
    widths = [9, 34, 12, 28, 11, 12, 24, 16, 9, 8, 11, 42, 13, 24, 36, 12, 36]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    for row_idx in range(2, len(records) + 2):
        ws.row_dimensions[row_idx].height = 42
    for cell in ws["M"][1:]:
        cell.number_format = "#,##0.00"
    ws.auto_filter.ref = f"A1:Q{max(1, len(records) + 1)}"


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
    issue_types = [item for item in ["性能", "外观", "加工"] if item in rules.get("issue_order", [])]
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
    costs: dict[tuple[str, int], float] = defaultdict(float)
    issue_totals_by_month: dict[int, int] = defaultdict(int)
    closed_by_month: dict[int, int] = defaultdict(int)
    processing_by_month: dict[int, int] = defaultdict(int)
    unresolved_by_month: dict[int, int] = defaultdict(int)
    cost_by_month: dict[int, float] = defaultdict(float)
    unknown_fee_count = 0

    for record in records:
        brand = record.get("brand") or "未知"
        month = record.get("month")
        if not month:
            continue
        if brand not in brands:
            brands.append(brand)
        primary_issue_type = record.get("primary_issue_type") or "其他"
        if primary_issue_type not in issue_types:
            primary_issue_type = "其他"
        counts[(brand, primary_issue_type, month)] += 1
        issue_totals_by_month[month] += 1
        fee_amount = record.get("fee_amount", record.get("cost"))
        if fee_amount is None:
            unknown_fee_count += 1
        elif record.get("cost_included", True):
            costs[(brand, month)] += float(fee_amount)
            cost_by_month[month] += float(fee_amount)
        resolution_status = record.get("resolution_status") or ("已解决" if record.get("closed") else "未解决")
        if resolution_status == "已解决":
            closed_by_month[month] += 1
        elif resolution_status == "处理中":
            processing_by_month[month] += 1
        else:
            unresolved_by_month[month] += 1

    row = 4
    serial = 1
    case_rows: list[int] = []
    fee_rows: list[int] = []
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
        fee_rows.append(row)
        ws.cell(row, 1, serial)
        ws.cell(row, 2, brand)
        ws.cell(row, 3, "费用")
        serial += 1
        total_cost = 0.0
        for col, month in enumerate(months, start=4):
            value = round(costs[(brand, month)], 2)
            total_cost += value
            ws.cell(row, col, value if value else 0)
            ws.cell(row, col).fill = fee_fill
        ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
        for col in range(1, last_col + 1):
            ws.cell(row, col).fill = fee_fill
        for col in range(4, last_col + 1):
            ws.cell(row, col).number_format = "0.00"
        if row > brand_start:
            ws.merge_cells(start_row=brand_start, start_column=2, end_row=row, end_column=2)
        row += 1

    subtotal_row = row
    ws.cell(row, 2, "售后小计")
    for col, month in enumerate(months, start=4):
        column = get_column_letter(col)
        ws.cell(row, col, f"=SUM({','.join(f'{column}{source_row}' for source_row in case_rows)})")
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    row += 1
    ws.cell(row, 2, "售后费用")
    for col, month in enumerate(months, start=4):
        column = get_column_letter(col)
        ws.cell(row, col, f"=SUM({','.join(f'{column}{source_row}' for source_row in fee_rows)})")
    ws.cell(row, last_col, f"=SUM(D{row}:O{row})")
    for col in range(4, last_col + 1):
        ws.cell(row, col).number_format = "0.00"
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
    ws.cell(row, 1, "1、转嫁给合作方或供应商的售后费用不在统计之列。")
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    row += 1
    ws.cell(row, 1, f"2、未知费用不计入金额合计；本页共有 {unknown_fee_count} 条费用为空或待确认。")
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
        ("fee_amount", "费用"),
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
        record for record in records
        if record.get("needs_review")
        or record.get("brand") in {"未知", "待确认"}
        or record.get("primary_issue_type") in {"其他", "待确认", None, ""}
        or record.get("fee_status") in {"not_found", "needs_review", "transferred"}
        or record.get("warnings")
    ]
    columns = [
        ("input_index", "输入序号"),
        ("source_file", "来源文件"),
        ("brand", "品牌"),
        ("complaint_date", "提出质量问题/报修日期"),
        ("primary_issue_type", "主原因"),
        ("fee_amount", "费用"),
        ("fee_status", "费用状态"),
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
    widths = [9, 36, 12, 20, 12, 13, 16, 12, 42, 46, 44, 32, 30, 12]
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:N{max(1, len(review_records) + 1)}"


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
