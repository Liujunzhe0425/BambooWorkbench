"""Deterministic ordering for multiple screening decisions on one batch."""

from __future__ import annotations

from moisture.domain.enums import ScreenStatus
from moisture.domain.models import ScreeningDecision


def _rule_id(decision: ScreeningDecision) -> str:
    return decision.rule_hits[0].rule_id if decision.rule_hits else ""


def _priority(decision: ScreeningDecision) -> tuple[int, str, str]:
    target = decision.target_field or ""
    if target in {"mean", "total_average"}:
        rank = 0
    elif decision.status is ScreenStatus.DATA_QUALITY:
        rank = 1
    elif target == "range_value":
        rank = 2
    else:
        rank = 3
    return rank, target, _rule_id(decision)


def ordered_decisions(
    decisions: tuple[ScreeningDecision, ...] | list[ScreeningDecision],
) -> tuple[ScreeningDecision, ...]:
    """Return a stable business-priority order independent of YAML ordering."""

    return tuple(sorted(decisions, key=_priority))


def primary_decision(decisions: tuple[ScreeningDecision, ...]) -> ScreeningDecision:
    ordered = ordered_decisions(decisions)
    return ordered[0] if ordered else ScreeningDecision(status=ScreenStatus.NORMAL)
