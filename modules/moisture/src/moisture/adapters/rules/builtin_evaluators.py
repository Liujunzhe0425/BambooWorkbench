"""Six deterministic evaluators migrated without changing their algorithms."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from operator import eq, ge, gt, le, lt, ne

from moisture.adapters.rules.evaluator_registry import RuleEvaluatorRegistry
from moisture.domain.enums import DisplayColor, ScreenStatus
from moisture.domain.models import DecisionTargetField, RuleHit, ScreeningDecision
from moisture.domain.rules import (
    PendingRuleMatch,
    RuleContext,
    RuleDefinition,
    RuleEvaluationResult,
    RulePackageSnapshot,
)
from moisture.domain.statistics import compute_batch_statistics

_OPERATORS = {">": gt, ">=": ge, "<": lt, "<=": le, "==": eq, "!=": ne}
_NUMERIC_TARGET_FIELDS: dict[str, DecisionTargetField] = {
    "total_average": "mean",
    "mean": "mean",
    "minimum": "minimum",
    "maximum": "maximum",
    "range_value": "range_value",
    "standard_deviation": "standard_deviation",
    "median": "median",
    "first_quartile": "first_quartile",
    "third_quartile": "third_quartile",
    "interquartile_range": "interquartile_range",
    "maximum_department_average_difference": "maximum_department_average_difference",
    "total_weight_kg": "total_weight_kg",
}


def _target_field(definition: RuleDefinition) -> DecisionTargetField | None:
    if definition.rule_type in {"numeric_threshold", "numeric_range"}:
        return _NUMERIC_TARGET_FIELDS.get(definition.field or "")
    if definition.rule_type == "department_difference":
        return "maximum_department_average_difference"
    return None


def _numeric_field(context: RuleContext, field: str) -> Decimal:
    statistics = context.statistics
    fields: dict[str, Decimal | None] = {
        "total_average": statistics.total_average,
        "mean": statistics.mean,
        "minimum": statistics.minimum,
        "maximum": statistics.maximum,
        "range_value": statistics.range_value,
        "standard_deviation": statistics.standard_deviation,
        "median": statistics.median,
        "first_quartile": statistics.first_quartile,
        "third_quartile": statistics.third_quartile,
        "interquartile_range": statistics.interquartile_range,
        "maximum_department_average_difference": (statistics.maximum_department_average_difference),
        "total_weight_kg": context.record.total_weight_kg,
    }
    if field not in fields:
        raise ValueError(f"unknown numeric field: {field}")
    value = fields[field]
    if value is None:
        raise ValueError(f"numeric field is missing: {field}")
    return value


def _hit(definition: RuleDefinition, message: str) -> tuple[RuleHit, ...]:
    return (
        RuleHit(
            rule_id=definition.rule_id,
            message=definition.message or message,
            display_color=definition.color,
            target_field=_target_field(definition),
        ),
    )


class NumericThresholdEvaluator:
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]:
        assert definition.field is not None
        assert definition.operator is not None
        assert definition.threshold is not None
        value = _numeric_field(context, definition.field)
        if _OPERATORS[definition.operator](value, definition.threshold):
            return _hit(
                definition,
                f"{definition.field} {definition.operator} {definition.threshold}",
            )
        return ()


class NumericRangeEvaluator:
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]:
        assert definition.field is not None
        assert definition.lower is not None
        assert definition.upper is not None
        assert definition.mode is not None
        inside = definition.lower <= _numeric_field(context, definition.field) <= definition.upper
        if inside is (definition.mode == "inside"):
            return _hit(definition, f"{definition.field} is {definition.mode} configured range")
        return ()


class MissingFieldEvaluator:
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]:
        record = context.record
        allowed_fields = {
            "supplier": record.supplier,
            "material_type": record.material_type,
            "arrival_date": record.arrival_date,
            "test_date": record.test_date,
            "total_weight_kg": record.total_weight_kg,
            "source_file": record.source_file,
            "source_sheet": record.source_sheet,
        }
        unknown = [field for field in definition.fields if field not in allowed_fields]
        if unknown:
            raise ValueError(f"unknown missing-field target: {unknown[0]}")
        missing = [field for field in definition.fields if allowed_fields[field] in {None, ""}]
        return _hit(definition, f"missing fields: {', '.join(missing)}") if missing else ()


class FormulaMismatchEvaluator:
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]:
        assert definition.tolerance is not None
        mismatches = [
            sample.sample_index
            for sample in context.record.samples
            if sample.source_moisture_value is not None
            and sample.verified_moisture_value is not None
            and abs(sample.source_moisture_value - sample.verified_moisture_value)
            > definition.tolerance
        ]
        return _hit(definition, f"formula mismatch at samples: {mismatches}") if mismatches else ()


class DepartmentDifferenceEvaluator:
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]:
        assert definition.operator is not None
        assert definition.threshold is not None
        difference = context.statistics.maximum_department_average_difference
        if difference is None:
            raise ValueError("department statistics are unavailable")
        if _OPERATORS[definition.operator](difference, definition.threshold):
            return _hit(definition, f"department average difference is {difference}")
        return ()


class CompositeEvaluator:
    def evaluate(self, context: RuleContext, definition: RuleDefinition) -> tuple[RuleHit, ...]:
        assert definition.combinator is not None
        for rule_id in definition.rule_ids:
            if rule_id not in context.hit_states:
                raise ValueError(f"unresolved composite rule ID: {rule_id}")
        states = [context.hit_states[rule_id] for rule_id in definition.rule_ids]
        matched = all(states) if definition.combinator == "AND" else any(states)
        return _hit(definition, f"{definition.combinator} composite matched") if matched else ()


def default_registry() -> RuleEvaluatorRegistry:
    registry = RuleEvaluatorRegistry()
    registry.register("numeric_threshold", NumericThresholdEvaluator())
    registry.register("numeric_range", NumericRangeEvaluator())
    registry.register("missing_field", MissingFieldEvaluator())
    registry.register("formula_mismatch", FormulaMismatchEvaluator())
    registry.register("department_difference", DepartmentDifferenceEvaluator())
    registry.register("composite", CompositeEvaluator())
    return registry


def _scope_matches(value: str | None, configured: tuple[str, ...]) -> bool:
    if not configured:
        return True
    allowed = {item.strip().casefold() for item in configured}
    return "all" in allowed or (value is not None and value.strip().casefold() in allowed)


def _season(observed: date | None) -> str | None:
    if observed is None:
        return None
    if observed.month in {3, 4, 5}:
        return "spring"
    if observed.month in {6, 7, 8}:
        return "summer"
    if observed.month in {9, 10, 11}:
        return "autumn"
    return "winter"


def _applies(context: RuleContext, definition: RuleDefinition) -> bool:
    record = context.record
    return (
        _scope_matches(record.material_type, definition.applicable_materials)
        and _scope_matches(
            _season(record.arrival_date or record.test_date), definition.applicable_seasons
        )
        and _scope_matches(record.supplier, definition.applicable_suppliers)
    )


def _decision(hit: RuleHit, definition: RuleDefinition) -> ScreeningDecision:
    if definition.rule_type in {"missing_field", "formula_mismatch"}:
        status = ScreenStatus.DATA_QUALITY
    elif hit.display_color == DisplayColor.ORANGE:
        status = ScreenStatus.HIGH
    elif hit.display_color == DisplayColor.GREEN:
        status = ScreenStatus.LOW
    else:
        status = ScreenStatus.NORMAL
    return ScreeningDecision(
        status=status,
        rule_hits=(hit,),
        display_color=hit.display_color,
        reason=hit.message,
        target_field=hit.target_field,
    )


def _pending(hit: RuleHit, definition: RuleDefinition, rules_sha256: str) -> PendingRuleMatch:
    if hit.display_color == DisplayColor.ORANGE:
        direction = "high"
    elif hit.display_color == DisplayColor.GREEN:
        direction = "low"
    elif definition.rule_type in {"missing_field", "formula_mismatch"}:
        direction = "data_quality"
    else:
        direction = "unspecified"
    return PendingRuleMatch(
        rule_id=definition.rule_id,
        message=hit.message,
        direction=direction,
        target_field=hit.target_field,
        threshold=definition.threshold,
        rules_sha256=rules_sha256,
    )


def evaluate_rules(
    record,
    snapshot: RulePackageSnapshot,
    registry: RuleEvaluatorRegistry | None = None,
) -> RuleEvaluationResult:
    active_registry = registry or default_registry()
    context = RuleContext(record=record, statistics=compute_batch_statistics(record))
    decisions: list[ScreeningDecision] = []
    pending: list[PendingRuleMatch] = []
    for definition in snapshot.definitions:
        evaluator = active_registry.get(definition.rule_type)
        if not _applies(context, definition):
            context.hit_states[definition.rule_id] = False
            continue
        hits = evaluator.evaluate(context, definition)
        context.hit_states[definition.rule_id] = bool(hits)
        if (
            snapshot.customer_confirmation_status == "confirmed"
            and definition.customer_confirmation_status == "confirmed"
        ):
            decisions.extend(_decision(hit, definition) for hit in hits)
        else:
            pending.extend(_pending(hit, definition, snapshot.rules_sha256) for hit in hits)
    return RuleEvaluationResult(decisions=tuple(decisions), pending_matches=tuple(pending))
