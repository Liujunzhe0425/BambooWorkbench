from __future__ import annotations

import math
import re
from typing import Any

AFTER_SALES_FEE_FIELD = "售后费用"
RESPONSIBLE_FACTORY_FIELD = "责任工厂"
COMPLAINT_TYPE_FIELD = "投诉类型"
REQUIRED_REVIEW_FIELDS = (
    AFTER_SALES_FEE_FIELD,
    RESPONSIBLE_FACTORY_FIELD,
    COMPLAINT_TYPE_FIELD,
)
DEFAULT_COMPLAINT_TYPES = ("性能", "外观", "加工", "其他")


def build_required_review_prompts(
    record: dict[str, Any], rules: dict[str, Any]
) -> list[dict[str, Any]]:
    """Create the mandatory per-case review prompts supported by the common UI."""

    fee = effective_after_sales_fee(record)
    factory = effective_responsible_factory(record) or "未知"
    complaint_types = _complaint_type_options(rules)
    primary = _text(record.get("primary_issue_type"))
    if primary not in complaint_types:
        primary = "其他"

    record.update(
        {
            "after_sales_fee_amount": fee,
            "after_sales_fee_status": "待人工复核",
            "after_sales_fee_reviewed": False,
            "responsible_factory": factory,
            "responsibility_reviewed": False,
            "complaint_type_reviewed": False,
            "mandatory_review_pending": True,
            "manual_review_completed": False,
            "needs_review": True,
        }
    )

    source_file = _text(record.get("source_file"))
    sheet = _text(record.get("sheet")) or None
    source_cells = record.get("source_cells")
    if not isinstance(source_cells, dict):
        source_cells = {}

    fee_text = "未识别到明确金额" if fee is None else f"当前建议 {fee:.2f} 元"
    return [
        _prompt(
            source_file=source_file,
            sheet=sheet,
            cell_or_range=_source_cells(source_cells, "solution", "application"),
            field=AFTER_SALES_FEE_FIELD,
            reason=(
                "请核对最终采用方案实际产生的售后费用，只填写数字金额；"
                f"确实无法确认时可留空。{fee_text}。"
            ),
            suggested_value=fee,
            options=[],
            confidence=1.0 if fee is not None else 0.0,
        ),
        _prompt(
            source_file=source_file,
            sheet=sheet,
            cell_or_range=_source_cells(
                source_cells, "responsibility", "investigation", "solution"
            ),
            field=RESPONSIBLE_FACTORY_FIELD,
            reason="请核对本案件最终承担责任的工厂或部门；原文没有明确时填写“未知”。",
            suggested_value=factory,
            options=[],
            confidence=0.9 if factory != "未知" else 0.0,
        ),
        _prompt(
            source_file=source_file,
            sheet=sheet,
            cell_or_range=_source_cells(source_cells, "investigation", "feedback"),
            field=COMPLAINT_TYPE_FIELD,
            reason="请根据调查结论复核主投诉类型；只能选择性能、外观、加工或其他。",
            suggested_value=primary,
            options=complaint_types,
            confidence=_confidence(record.get("issue_confidence")),
        ),
    ]


def apply_business_review_value(record: dict[str, Any], field: str, value: Any) -> bool:
    """Apply one business-review answer and return whether the field was handled."""

    if field == AFTER_SALES_FEE_FIELD:
        amount = _review_amount(value)
        record.update(
            {
                "after_sales_fee_amount": amount,
                "after_sales_fee_status": "已复核" if amount is not None else "复核后未知",
                "after_sales_fee_evidence": (
                    "竹简工作台人工复核值"
                    if amount is not None
                    else "竹简工作台人工复核：金额留空"
                ),
                "after_sales_fee_reviewed": True,
                "fee_amount": amount,
                "cost": amount,
                "enterprise_cost_amount": amount,
                "enterprise_cost_status": "exact" if amount is not None else "not_found",
                "enterprise_cost_evidence": (
                    "竹简工作台人工复核值"
                    if amount is not None
                    else "竹简工作台人工复核：金额留空"
                ),
                "enterprise_cost_reviewed": True,
                "fee_status": "exact" if amount is not None else "not_found",
                "cost_included": amount is not None,
                "cost_status": "人工复核确认" if amount is not None else "人工复核后未知",
                "cost_evidence": (
                    "竹简工作台人工复核值"
                    if amount is not None
                    else "竹简工作台人工复核：金额留空"
                ),
            }
        )
        refresh_manual_review_state(record)
        return True

    if field == RESPONSIBLE_FACTORY_FIELD:
        factory = _text(value) or "未知"
        record.update(
            {
                "responsible_factory": factory,
                "responsibility_reviewed": True,
                "responsibility_review_evidence": "竹简工作台人工复核值",
            }
        )
        refresh_manual_review_state(record)
        return True

    if field == COMPLAINT_TYPE_FIELD:
        complaint_type = _text(value)
        if complaint_type not in DEFAULT_COMPLAINT_TYPES:
            raise ValueError("投诉类型必须为性能、外观、加工或其他")
        record.update(
            {
                "primary_issue_type": complaint_type,
                "issue_types": [complaint_type],
                "issue_confidence": 1.0,
                "complaint_type_reviewed": True,
                "complaint_type_review_evidence": "竹简工作台人工复核值",
            }
        )
        refresh_manual_review_state(record)
        return True

    return False


def refresh_manual_review_state(record: dict[str, Any]) -> None:
    completed = all(
        bool(record.get(key))
        for key in (
            "after_sales_fee_reviewed",
            "responsibility_reviewed",
            "complaint_type_reviewed",
        )
    )
    record["manual_review_completed"] = completed
    record["mandatory_review_pending"] = not completed
    if completed:
        record["reviewed"] = True


def effective_after_sales_fee(record: dict[str, Any]) -> float | None:
    """Return the reviewed value, otherwise infer the selected solution's case total."""

    if record.get("after_sales_fee_reviewed"):
        return _amount(record, "after_sales_fee_amount")
    prepared = _amount(record, "after_sales_fee_amount")
    if prepared is not None:
        return prepared

    solution = _text(record.get("selected_solution")) or _text(record.get("solution"))
    enterprise = _amount(record, "enterprise_cost_amount", "fee_amount", "cost")
    external = _amount(record, "external_borne_amount")

    total_patterns = (
        r"(?:合计总费用|总计(?:材料)?费用|预计总费用)[^。；]{0,100}?"
        r"(?:=|为|约)?\s*(\d+(?:\.\d+)?)\s*元",
        r"预估[^。；]{0,60}?=\s*(\d+(?:\.\d+)?)\s*元",
    )
    totals: list[float] = []
    for pattern in total_patterns:
        totals.extend(float(item) for item in re.findall(pattern, solution))
    if totals:
        return round(totals[-1], 2)

    if enterprise is not None and external is not None:
        has_enterprise = f"{enterprise:g}" in solution
        has_external = f"{external:g}" in solution
        if has_enterprise and has_external:
            return round(enterprise + external, 2)
        return external if has_external else enterprise
    if external is not None:
        return external
    if enterprise is not None:
        return enterprise

    explicit_results = re.findall(r"=\s*(\d+(?:\.\d+)?)\s*元", solution)
    if explicit_results:
        return round(float(explicit_results[-1]), 2)
    return None


def effective_responsible_factory(record: dict[str, Any]) -> str:
    if record.get("responsibility_reviewed"):
        return _text(record.get("responsible_factory")) or "未知"
    reviewed_candidate = _text(record.get("responsible_factory"))
    if reviewed_candidate:
        return reviewed_candidate
    explicit = _text(record.get("responsibility"))
    text = "；".join(
        (explicit, _text(record.get("investigation")), _text(record.get("solution")))
    )
    patterns = (
        r"(?:责任工厂|责任部门|责任单位)\s*[:：]?\s*([^。；，]{2,30})",
        r"责任(?:由|方为|主体为)\s*([^。；，]{2,30}?)\s*(?:承担|负责|$)",
        r"由\s*([^。；，]{2,30}?)\s*(?:承担|负责)",
        r"(?:^|[。；])\s*([^。；]{2,40}?)\s*(?:共同)?承担(?:责任)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            candidate = _clean_factory_candidate(match.group(1))
            if candidate:
                return candidate
    return explicit


def _prompt(
    *,
    source_file: str,
    sheet: str | None,
    cell_or_range: str | None,
    field: str,
    reason: str,
    suggested_value: Any,
    options: list[str],
    confidence: float,
) -> dict[str, Any]:
    return {
        "source_file": source_file,
        "sheet": sheet,
        "cell_or_range": cell_or_range,
        "field": field,
        "reason": reason,
        "suggested_value": suggested_value,
        "options": options,
        "confidence": confidence,
        "blocking": True,
        "batch_applicable": False,
        "rememberable": False,
    }


def _complaint_type_options(rules: dict[str, Any]) -> list[str]:
    configured = rules.get("issue_order")
    if not isinstance(configured, list):
        return list(DEFAULT_COMPLAINT_TYPES)
    options = [str(item) for item in configured if str(item) in DEFAULT_COMPLAINT_TYPES]
    return options or list(DEFAULT_COMPLAINT_TYPES)


def _source_cells(source_cells: dict[str, Any], *keys: str) -> str | None:
    values = [_text(source_cells.get(key)) for key in keys]
    values = [value for value in values if value]
    return ",".join(values) or None


def _clean_factory_candidate(value: Any) -> str:
    candidate = _text(value).strip(" ：:，,。；;")
    candidate = re.sub(r"(?:共同)?承担(?:责任.*)?$", "", candidate).strip()
    if any(keyword in candidate for keyword in ("客户", "供应商", "合作方")):
        return ""
    return candidate


def _review_amount(value: Any) -> float | None:
    text = _text(value).replace(",", "").replace("元", "").replace("￥", "")
    if not text:
        return None
    try:
        amount = float(text)
    except ValueError as exc:
        raise ValueError("售后费用必须填写数字金额或留空") from exc
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("售后费用必须是大于或等于 0 的有限数字")
    return round(amount, 2)


def _amount(record: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return round(float(value), 2)
        match = re.search(r"-?\d+(?:\.\d+)?", _text(value).replace(",", ""))
        if match:
            return round(float(match.group()), 2)
    return None


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
