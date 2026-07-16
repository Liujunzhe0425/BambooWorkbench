from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from moisture.adapters.rules.builtin_evaluators import default_registry, evaluate_rules
from moisture.adapters.rules.evaluator_registry import RuleEvaluatorRegistry
from moisture.domain.enums import DisplayColor, ScreenStatus
from moisture.domain.models import BatchRecord, SampleMeasurement
from moisture.domain.rules import RuleDefinition, RulePackageSnapshot


def sample(
    index: int,
    value: str,
    *,
    department: str = "品质",
    source_value: str | None = None,
    verified_value: str | None = None,
) -> SampleMeasurement:
    used = Decimal(value)
    return SampleMeasurement(
        sample_index=index,
        department_raw=department,
        department=department,
        source_row=index + 4,
        initial_mass=Decimal("100"),
        dry_mass=Decimal("52"),
        foil_mass=Decimal("4"),
        source_moisture_value=Decimal(source_value) if source_value else used,
        verified_moisture_value=Decimal(verified_value) if verified_value else used,
        value_used_for_statistics=used,
    )


def batch(*samples: SampleMeasurement, supplier: str | None = "青山") -> BatchRecord:
    return BatchRecord(record_id="R", samples=samples, supplier=supplier)


def snapshot(
    *definitions: RuleDefinition, package_status: str = "confirmed"
) -> RulePackageSnapshot:
    return RulePackageSnapshot(
        schema_version="1.0",
        package_id="test-package",
        rule_version="test-v1",
        rules_file="rules.yaml",
        rules_sha256="a" * 64,
        source="test fixture",
        applicable_scope="test only",
        customer_confirmation_status=package_status,
        released_at="2026-07-16T00:00:00+08:00",
        module_version="0.1.0",
        definitions=definitions,
    )


def threshold(
    rule_id: str,
    operator: str,
    value: str,
    color: DisplayColor,
    *,
    status: str = "confirmed",
) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        rule_type="numeric_threshold",
        field="total_average",
        operator=operator,
        threshold=Decimal(value),
        color=color,
        customer_confirmation_status=status,
    )


def test_only_confirmed_rules_auto_evaluate() -> None:
    result = evaluate_rules(
        batch(sample(1, "0.60")),
        snapshot(threshold("HIGH", ">", "0.55", DisplayColor.ORANGE)),
    )

    assert result.pending_matches == ()
    assert result.decisions[0].status == ScreenStatus.HIGH
    assert result.decisions[0].display_color == DisplayColor.ORANGE


def test_pending_rule_requires_confirmation_without_auto_decision() -> None:
    pending = threshold("HIGH", ">", "0.55", DisplayColor.ORANGE, status="pending_confirmation")

    result = evaluate_rules(batch(sample(1, "0.60")), snapshot(pending))

    assert result.decisions == ()
    assert result.pending_matches[0].rule_id == "HIGH"
    assert result.pending_matches[0].direction == "high"
    assert result.pending_matches[0].threshold == Decimal("0.55")


def test_pending_package_cannot_auto_evaluate_a_confirmed_definition() -> None:
    confirmed = threshold("HIGH", ">", "0.55", DisplayColor.ORANGE)

    result = evaluate_rules(
        batch(sample(1, "0.60")),
        snapshot(confirmed, package_status="pending_confirmation"),
    )

    assert result.decisions == ()
    assert [match.rule_id for match in result.pending_matches] == ["HIGH"]


def test_numeric_range_missing_formula_department_and_composite_are_migrated() -> None:
    definitions = (
        RuleDefinition(
            rule_id="RANGE",
            rule_type="numeric_range",
            field="total_average",
            lower=Decimal("0.45"),
            upper=Decimal("0.55"),
            mode="outside",
            color=DisplayColor.ORANGE,
        ),
        RuleDefinition(rule_id="MISSING", rule_type="missing_field", fields=("supplier",)),
        RuleDefinition(
            rule_id="FORMULA",
            rule_type="formula_mismatch",
            tolerance=Decimal("0.0001"),
        ),
        RuleDefinition(
            rule_id="DEPT",
            rule_type="department_difference",
            operator=">",
            threshold=Decimal("0.10"),
            color=DisplayColor.ORANGE,
        ),
        RuleDefinition(
            rule_id="COMBO",
            rule_type="composite",
            rule_ids=("RANGE", "DEPT"),
            combinator="AND",
        ),
    )
    record = batch(
        sample(1, "0.40", department="一厂", source_value="0.10", verified_value="0.40"),
        sample(2, "0.80", department="品质"),
        supplier=None,
    )

    result = evaluate_rules(record, snapshot(*definitions))

    assert {hit.rule_id for decision in result.decisions for hit in decision.rule_hits} == {
        "RANGE",
        "MISSING",
        "FORMULA",
        "DEPT",
        "COMBO",
    }


def test_scope_matches_material_season_and_supplier() -> None:
    scoped = replace(
        threshold("SCOPED", ">", "0.55", DisplayColor.ORANGE),
        applicable_materials=("竹丝",),
        applicable_seasons=("summer",),
        applicable_suppliers=("supplier-a",),
    )
    matching = replace(
        batch(sample(1, "0.60"), supplier="Supplier-A"),
        material_type="竹丝",
        arrival_date=date(2026, 7, 1),
    )

    assert len(evaluate_rules(matching, snapshot(scoped)).decisions) == 1
    assert evaluate_rules(replace(matching, material_type="木材"), snapshot(scoped)).decisions == ()
    assert (
        evaluate_rules(replace(matching, arrival_date=date(2026, 1, 1)), snapshot(scoped)).decisions
        == ()
    )
    assert (
        evaluate_rules(replace(matching, supplier="supplier-b"), snapshot(scoped)).decisions == ()
    )


def test_unknown_and_duplicate_evaluators_fail_closed() -> None:
    registry = RuleEvaluatorRegistry()
    evaluator = default_registry().get("numeric_threshold")
    registry.register("numeric_threshold", evaluator)

    with pytest.raises(ValueError, match="duplicate rule type"):
        registry.register("numeric_threshold", evaluator)
    with pytest.raises(ValueError, match="unknown rule type"):
        registry.get("python_eval")

    unknown = RuleDefinition(rule_id="UNKNOWN", rule_type="python_eval")
    with pytest.raises(ValueError, match="unknown rule type"):
        evaluate_rules(batch(sample(1, "0.50")), snapshot(unknown))


def test_default_registry_contains_only_six_migrated_types() -> None:
    assert default_registry().registered_types == frozenset(
        {
            "numeric_threshold",
            "numeric_range",
            "missing_field",
            "formula_mismatch",
            "department_difference",
            "composite",
        }
    )
