"""Human-readable screening metadata derived from the active rule snapshot."""

from __future__ import annotations

from decimal import Decimal

from moisture.domain.enums import ScreenStatus
from moisture.domain.rules import RuleEvaluationResult


def screening_bounds(
    evaluation: RuleEvaluationResult,
) -> tuple[Decimal | None, Decimal | None]:
    """Return the applicable confirmed-style lower and upper screening bounds."""

    lower: Decimal | None = None
    upper: Decimal | None = None
    for definition in evaluation.applicable_definitions:
        if definition.rule_type != "numeric_threshold" or definition.field != "total_average":
            continue
        if definition.operator in {"<", "<="}:
            lower = definition.threshold
        elif definition.operator in {">", ">="}:
            upper = definition.threshold
    return lower, upper


def _percent(value: Decimal | None) -> str:
    if value is None:
        return "规则阈值"
    return f"{value * 100:.2f}%"


def screening_suggestion(
    status: ScreenStatus,
    lower: Decimal | None,
    upper: Decimal | None,
    *,
    pending: bool = False,
) -> str:
    if pending:
        return "待业务确认规则未自动参与判定"
    if status is ScreenStatus.HIGH:
        return f"均值高于{_percent(upper)}，建议复核取样、烘干和称量记录"
    if status is ScreenStatus.LOW:
        return f"均值低于{_percent(lower)}，建议复核取样代表性和称量记录"
    if status is ScreenStatus.DATA_QUALITY:
        return "发现数据质量疑点，建议复核原始记录和公式"
    return "未命中已确认筛查规则"
