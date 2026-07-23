from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from after_sales_agent.manual_review import effective_after_sales_fee

ISSUE_ORDER = ("性能", "外观", "加工", "其他")


def build_analysis_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary_records = [record for record in records if record.get("included_in_summary", True)]
    issue_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    monthly: dict[tuple[int | None, int | None], dict[str, float | int | str]] = defaultdict(
        lambda: {
            "case_count": 0,
            "after_sales_fee_amount": 0.0,
            "enterprise_cost_amount": 0.0,
            "internal_accountability_amount": 0.0,
            "external_borne_amount": 0.0,
        }
    )
    unknown_enterprise_cost_count = 0
    unknown_brand_count = 0
    unknown_date_count = 0
    ai_assisted_count = 0
    ai_degraded_count = 0
    offline_rule_count = 0

    for record in summary_records:
        key = (_as_int(record.get("year")), _as_int(record.get("month")))
        bucket = monthly[key]
        bucket["case_count"] = int(bucket["case_count"]) + 1
        reviewed_fee = effective_after_sales_fee(record)
        if reviewed_fee is not None:
            bucket["after_sales_fee_amount"] = (
                float(bucket["after_sales_fee_amount"]) + reviewed_fee
            )
        for field in (
            "enterprise_cost_amount",
            "internal_accountability_amount",
            "external_borne_amount",
        ):
            amount = _amount(record.get(field))
            if amount is not None:
                bucket[field] = float(bucket[field]) + amount

        tags = record.get("issue_types")
        if not isinstance(tags, list) or not tags:
            tags = [record.get("primary_issue_type") or "其他"]
        normalized = {str(tag) if str(tag) in ISSUE_ORDER else "其他" for tag in tags}
        issue_counts.update(normalized)

        status = str(
            record.get("resolution_status") or ("已解决" if record.get("closed") else "未解决")
        )
        if status not in {"已解决", "处理中", "未解决"}:
            status = "未解决"
        status_counts[status] += 1

        if record.get("enterprise_cost_amount", record.get("fee_amount")) is None:
            unknown_enterprise_cost_count += 1
        if str(record.get("brand") or "未知") == "未知":
            unknown_brand_count += 1
        if record.get("year") is None or record.get("month") is None:
            unknown_date_count += 1
        analysis_status = str(record.get("analysis_status") or "")
        if record.get("issue_analysis_source") == "api":
            ai_assisted_count += 1
        elif "降级" in analysis_status:
            ai_degraded_count += 1
        else:
            offline_rule_count += 1

    monthly_rows: list[dict[str, Any]] = []
    for (year, month), values in sorted(monthly.items(), key=_period_sort_key):
        monthly_rows.append(
            {
                "year": year,
                "month": month,
                "period": _period_label(year, month),
                "case_count": int(values["case_count"]),
                "after_sales_fee_amount": round(float(values["after_sales_fee_amount"]), 2),
                "enterprise_cost_amount": round(float(values["enterprise_cost_amount"]), 2),
                "internal_accountability_amount": round(
                    float(values["internal_accountability_amount"]), 2
                ),
                "external_borne_amount": round(float(values["external_borne_amount"]), 2),
            }
        )

    return {
        "case_count": len(summary_records),
        "issue_counts": {issue: int(issue_counts.get(issue, 0)) for issue in ISSUE_ORDER},
        "status_counts": {
            "已解决": int(status_counts.get("已解决", 0)),
            "处理中": int(status_counts.get("处理中", 0)),
            "未解决": int(status_counts.get("未解决", 0)),
        },
        "monthly": monthly_rows,
        "totals": {
            "after_sales_fee_amount": round(
                sum(effective_after_sales_fee(record) or 0.0 for record in summary_records),
                2,
            ),
            "enterprise_cost_amount": round(
                sum(
                    _amount(r.get("enterprise_cost_amount", r.get("fee_amount"))) or 0.0
                    for r in summary_records
                ),
                2,
            ),
            "internal_accountability_amount": round(
                sum(
                    _amount(r.get("internal_accountability_amount")) or 0.0 for r in summary_records
                ),
                2,
            ),
            "external_borne_amount": round(
                sum(_amount(r.get("external_borne_amount")) or 0.0 for r in summary_records), 2
            ),
        },
        "risks": {
            "unknown_enterprise_cost_count": unknown_enterprise_cost_count,
            "unknown_brand_count": unknown_brand_count,
            "unknown_date_count": unknown_date_count,
        },
        "analysis_sources": {
            "ai_assisted_count": ai_assisted_count,
            "ai_degraded_count": ai_degraded_count,
            "offline_rule_count": offline_rule_count,
        },
    }


def write_analysis_report(
    records: list[dict[str, Any]],
    result: dict[str, Any],
    output_path: Path,
) -> None:
    metrics = build_analysis_metrics(records)
    summary = result.get("summary", {})
    pending_count = int(summary.get("confirmation_count") or 0)
    status_counts = metrics["status_counts"]
    issue_counts = metrics["issue_counts"]
    monthly = metrics["monthly"]
    totals = metrics["totals"]
    risks = metrics["risks"]
    analysis_sources = metrics["analysis_sources"]

    top_issue = max(issue_counts, key=issue_counts.get) if any(issue_counts.values()) else None
    high_cost = max(monthly, key=lambda item: item["enterprise_cost_amount"], default=None)
    lines = [
        "# 售后分析报告",
        "",
        "本报告由结构化售后记录自动汇总生成，仅用于业务复核和趋势观察，不替代责任认定、财务入账、赔偿审批或正式结案。",
        "",
        "## 运行概况",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| 输入文件 | {int(summary.get('input_count') or 0)} |",
        f"| 成功处理 | {int(summary.get('processed_count') or 0)} |",
        f"| 处理失败 | {int(summary.get('failed_count') or 0)} |",
        f"| 待人工复核项 | {pending_count} |",
        "",
        "## 分析来源",
        "",
        f"- AI辅助分析：{analysis_sources['ai_assisted_count']} 件",
        f"- AI不可用后降级为离线规则：{analysis_sources['ai_degraded_count']} 件",
        f"- 离线规则或无需AI辅助：{analysis_sources['offline_rule_count']} 件",
        "",
        "AI只辅助问题类型、原因摘要、证据引用和复核建议；售后费用、责任工厂、"
        "赔偿/责任认定及结案状态不由AI决定。",
        "",
        "## 问题类型分析",
        "",
        "问题分类采用多标签统计，同一案件可同时计入多个类型，分类数量不能相加作为案件总数。",
        "",
        "| 问题类型 | 标签数量 |",
        "|---|---:|",
    ]
    lines.extend(f"| {issue} | {issue_counts[issue]} |" for issue in ISSUE_ORDER)
    lines.extend(["", f"案件总数（每案计一次）：{metrics['case_count']}。"])
    if top_issue:
        lines.append(f"当前标签数量最多的是“{top_issue}”，共 {issue_counts[top_issue]} 条。")
    else:
        lines.append("本次没有可用于问题类型分析的有效案件。")

    lines.extend(
        [
            "",
            "## 月度案件与金额",
            "",
            "| 报修月份 | 案件数 | 售后费用（元） | 企业售后成本（元） | "
            "内部责任扣款（元） | 外部承担金额（元） |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    if monthly:
        for item in monthly:
            prefix = (
                f"| {item['period']} | {item['case_count']} | "
                f"{item['after_sales_fee_amount']:.2f} | "
            )
            lines.append(
                prefix
                + f"{item['enterprise_cost_amount']:.2f} | "
                + f"{item['internal_accountability_amount']:.2f} | "
                + f"{item['external_borne_amount']:.2f} |"
            )
    else:
        lines.append("| 无有效月份数据 | 0 | 0.00 | 0.00 | 0.00 | 0.00 |")
    lines.extend(
        [
            "",
            f"人工复核口径售后费用合计：{totals['after_sales_fee_amount']:.2f} 元；"
            f"企业售后成本合计：{totals['enterprise_cost_amount']:.2f} 元；"
            f"内部责任扣款合计：{totals['internal_accountability_amount']:.2f} 元；"
            f"外部承担金额合计：{totals['external_borne_amount']:.2f} 元。",
        ]
    )
    if high_cost and high_cost["enterprise_cost_amount"] > 0:
        lines.append(
            f"企业售后成本最高的统计月份是 {high_cost['period']}，金额为 "
            f"{high_cost['enterprise_cost_amount']:.2f} 元。"
        )
    else:
        lines.append("本次没有可确认的企业售后成本高峰月份。")

    lines.extend(
        [
            "",
            "## 案件处理状态",
            "",
            f"- 已解决：{status_counts['已解决']} 件",
            f"- 处理中：{status_counts['处理中']} 件",
            f"- 未解决：{status_counts['未解决']} 件",
            "",
            "## 数据风险",
            "",
            f"- 企业售后成本为空或待确认：{risks['unknown_enterprise_cost_count']} 件",
            f"- 品牌未知：{risks['unknown_brand_count']} 件",
            f"- 报修年份或月份缺失：{risks['unknown_date_count']} 件",
            f"- 文件处理失败：{int(summary.get('failed_count') or 0)} 件",
            f"- 尚未完成的人工复核项：{pending_count} 项",
            "",
            "## 建议的下一步",
            "",
        ]
    )
    suggestions: list[str] = []
    if pending_count:
        suggestions.append("逐项核对待人工复核字段，并在确认原文依据后再用于正式统计。")
    if risks["unknown_enterprise_cost_count"]:
        suggestions.append("优先补齐企业实际承担的材料、运费、人工、返工、赔偿或差旅凭据。")
    if status_counts["处理中"] or status_counts["未解决"]:
        suggestions.append("跟进处理中和未解决案件的实际完成记录，未见完成证据前不要自动结案。")
    if risks["unknown_brand_count"]:
        suggestions.append("根据产品或品牌字段补录未知品牌，不使用客户名称代替品牌。")
    if int(summary.get("failed_count") or 0):
        suggestions.append("重新导出失败的工作簿后单独重试，避免遗漏本批次案件。")
    if not suggestions:
        suggestions.append("抽查金额凭据和结案证据，确认无误后再进入后续审批或财务流程。")
    lines.extend(f"- {item}" for item in suggestions)
    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _period_sort_key(item: tuple[tuple[int | None, int | None], Any]) -> tuple[int, int, int]:
    (year, month), _ = item
    return (0 if year is not None else 1, year or 9999, month or 99)


def _period_label(year: int | None, month: int | None) -> str:
    if year is not None and month is not None:
        return f"{year}年{month}月"
    if month is not None:
        return f"年份未注明·{month}月"
    return "报修日期未注明"
