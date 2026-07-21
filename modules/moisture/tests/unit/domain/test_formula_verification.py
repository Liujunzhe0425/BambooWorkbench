import sys
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.domain.formula_verification import verify_moisture  # noqa: E402


def test_formula_match_uses_source_value() -> None:
    result = verify_moisture(Decimal("100"), Decimal("52"), Decimal("4"), Decimal("0.5"))

    assert result.status == "matched"
    assert result.verified_value == Decimal("0.5")
    assert result.value_used == Decimal("0.5")


def test_formula_with_zero_denominator_has_no_usable_value() -> None:
    result = verify_moisture(Decimal("4"), Decimal("3"), Decimal("4"), Decimal("0.2"))

    assert result.status == "invalid_denominator"
    assert result.verified_value is None
    assert result.value_used is None


def test_formula_without_source_result_uses_verified_value() -> None:
    result = verify_moisture(Decimal("100"), Decimal("52"), Decimal("4"), None)

    assert result.status == "source_result_unavailable"
    assert result.verified_value == Decimal("0.5")
    assert result.value_used == Decimal("0.5")


def test_formula_difference_at_tolerance_matches() -> None:
    result = verify_moisture(
        Decimal("100"),
        Decimal("52"),
        Decimal("4"),
        Decimal("0.5001"),
        tolerance=Decimal("0.0001"),
    )

    assert result.status == "matched"
    assert result.value_used == Decimal("0.5001")


def test_formula_difference_over_tolerance_is_mismatch_and_keeps_source_value() -> None:
    result = verify_moisture(
        Decimal("100"),
        Decimal("52"),
        Decimal("4"),
        Decimal("0.5002"),
        tolerance=Decimal("0.0001"),
    )

    assert result.status == "mismatch"
    assert result.verified_value == Decimal("0.5")
    assert result.value_used == Decimal("0.5002")


def test_formula_rejects_negative_tolerance() -> None:
    with pytest.raises(ValueError, match="tolerance must be non-negative"):
        verify_moisture(
            Decimal("100"),
            Decimal("52"),
            Decimal("4"),
            Decimal("0.5"),
            tolerance=Decimal("-0.0001"),
        )
