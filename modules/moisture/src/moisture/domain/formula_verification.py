"""Independent verification of the moisture formula used by source workbooks."""

from decimal import Decimal
from typing import Literal

from moisture.domain.models import FormulaVerification


def verify_moisture(
    initial_mass: Decimal,
    dry_mass: Decimal,
    foil_mass: Decimal,
    source_value: Decimal | None,
    tolerance: Decimal = Decimal("0.0001"),
) -> FormulaVerification:
    if tolerance < 0:
        raise ValueError("tolerance must be non-negative")

    denominator = initial_mass - foil_mass
    if denominator == 0:
        return FormulaVerification(
            status="invalid_denominator",
            verified_value=None,
            value_used=None,
        )

    verified = (initial_mass - dry_mass) / denominator
    if source_value is None:
        return FormulaVerification(
            status="source_result_unavailable",
            verified_value=verified,
            value_used=verified,
        )

    status: Literal["matched", "mismatch"] = (
        "matched" if abs(source_value - verified) <= tolerance else "mismatch"
    )
    return FormulaVerification(status=status, verified_value=verified, value_used=source_value)
