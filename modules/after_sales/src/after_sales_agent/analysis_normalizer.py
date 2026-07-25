from __future__ import annotations

from typing import Any


def normalize_analysis(parsed: dict[str, Any], categories: list[str]) -> dict[str, Any]:
    raw_types = parsed.get("issue_types") or []
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    issue_types: list[str] = []
    for item in raw_types:
        normalized = normalize_category(str(item), categories)
        if normalized and normalized not in issue_types:
            issue_types.append(normalized)
    if not issue_types:
        issue_types = ["其他"]

    primary = (
        normalize_category(str(parsed.get("primary_issue_type") or issue_types[0]), categories)
        or issue_types[0]
    )
    evidence = parsed.get("evidence") or []
    if isinstance(evidence, str):
        evidence = [evidence]

    cost_items = normalize_cost_items(parsed.get("cost_items"))
    resolution_status = normalize_resolution_status(
        parsed.get("resolution_status"), parsed.get("closed")
    )

    return {
        "brand_name": normalize_brand_name(parsed.get("brand_name")),
        "brand_reason": clean_text(parsed.get("brand_reason")),
        "after_sales_year": parse_optional_int(parsed.get("after_sales_year")),
        "after_sales_month": parse_month(parsed.get("after_sales_month")),
        "issue_types": issue_types,
        "primary_issue_type": primary,
        "reason_summary": clean_text(parsed.get("reason_summary")),
        "evidence": [clean_text(item) for item in evidence if clean_text(item)][:8],
        "responsible_factory": normalize_brand_name(parsed.get("responsible_factory")),
        "responsible_factory_reason": clean_text(parsed.get("responsible_factory_reason")),
        "selected_solution": clean_text(parsed.get("selected_solution")),
        "cost_items": cost_items,
        "cost_amount": parse_optional_float(parsed.get("cost_amount"), default=None),
        "cost_included": parse_bool(parsed.get("cost_included"), True),
        "cost_reason": clean_text(parsed.get("cost_reason")),
        "resolution_status": resolution_status,
        "resolution_reason": clean_text(
            parsed.get("resolution_reason") or parsed.get("closed_reason")
        ),
        "closed": resolution_status == "已解决",
        "closed_reason": clean_text(parsed.get("resolution_reason") or parsed.get("closed_reason")),
        "confidence": clamp_float(parsed.get("confidence"), 0.0, 1.0),
        "needs_manual_review": parse_bool(
            parsed.get("needs_manual_review"), clamp_float(parsed.get("confidence"), 0.0, 1.0) < 0.7
        ),
    }


def normalize_brand_name(value: Any) -> str:
    text = clean_text(value)
    if not text or text in {"未识别", "无法识别", "无法判断", "不明确", "无", "null", "None"}:
        return "未知"
    return text


def normalize_resolution_status(value: Any, legacy_closed: Any = None) -> str:
    text = clean_text(value)
    if text in {"已解决", "处理中", "未解决"}:
        return text
    if text in {"完成", "已完成", "已处理", "已关闭", "结案"}:
        return "已解决"
    if text in {"待处理", "进行中", "执行中", "待执行"}:
        return "处理中"
    if text in {"未处理", "无方案"}:
        return "未解决"
    return "已解决" if parse_bool(legacy_closed, False) else "未解决"


def normalize_category(value: str, categories: list[str]) -> str | None:
    value = value.strip()
    if value in categories:
        return value
    mapping = {
        "加工": "加工",
        "尺寸": "加工",
        "安装": "加工",
        "功能": "加工",
        "功能性": "加工",
        "质量": "性能",
        "材料": "性能",
        "观感": "外观",
    }
    if value in mapping and mapping[value] in categories:
        return mapping[value]
    for category in categories:
        if category in value:
            return category
    return None


def normalize_cost_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value[:30]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "name": clean_text(item.get("name")) or "售后费用",
                "amount": parse_optional_float(item.get("amount"), default=0.0),
                "included": parse_bool(item.get("included"), True),
                "evidence": clean_text(item.get("evidence")),
            }
        )
    return items


def parse_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def parse_month(value: Any) -> int | None:
    month = parse_optional_int(value)
    if month and 1 <= month <= 12:
        return month
    return None


def parse_optional_float(value: Any, default: float | None = 0.0) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = low
    return max(low, min(high, number))


def parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "是", "已", "已完成"}:
        return True
    if text in {"false", "0", "no", "n", "否", "未", "未完成"}:
        return False
    return default


def clean_text(value: Any) -> str:
    return str(value or "").strip()
