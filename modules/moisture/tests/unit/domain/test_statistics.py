import sys
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.domain.models import BatchRecord, SampleMeasurement  # noqa: E402
from moisture.domain.statistics import compute_batch_statistics  # noqa: E402


def sample(index: int, department: str, value: str | None) -> SampleMeasurement:
    decimal_value = Decimal(value) if value is not None else None
    return SampleMeasurement(
        sample_index=index,
        department_raw=department,
        department=department,
        source_row=index + 4,
        initial_mass=Decimal("100"),
        dry_mass=Decimal("52"),
        foil_mass=Decimal("4"),
        source_moisture_value=decimal_value,
        verified_moisture_value=decimal_value,
        value_used_for_statistics=decimal_value,
    )


def test_statistics_include_batch_distribution_and_departments() -> None:
    record = BatchRecord.minimal(
        "R4",
        [
            sample(1, "一厂", "0.4"),
            sample(2, "一厂", "0.5"),
            sample(3, "品质", "0.6"),
            sample(4, "品质", "0.7"),
        ],
    )

    result = compute_batch_statistics(record)

    assert result.sample_count == 4
    assert result.mean == Decimal("0.55")
    assert result.total_average == Decimal("0.55")
    assert result.minimum == Decimal("0.4")
    assert result.maximum == Decimal("0.7")
    assert result.range_value == Decimal("0.3")
    assert result.median == Decimal("0.55")
    assert result.first_quartile == Decimal("0.475")
    assert result.third_quartile == Decimal("0.625")
    assert result.interquartile_range == Decimal("0.150")
    assert result.department_averages == {
        "一厂": Decimal("0.45"),
        "品质": Decimal("0.65"),
    }
    assert result.maximum_department_average_difference == Decimal("0.20")
    assert isinstance(result.standard_deviation, Decimal)
    assert result.standard_deviation == pytest.approx(Decimal("0.12909944487358055"))


def test_single_usable_sample_has_no_standard_deviation() -> None:
    result = compute_batch_statistics(BatchRecord.minimal("R1", [sample(1, "品质", "0.5")]))

    assert result.sample_count == 1
    assert result.standard_deviation is None
    assert result.first_quartile == Decimal("0.5")
    assert result.third_quartile == Decimal("0.5")
    assert result.interquartile_range == Decimal("0")
    assert result.maximum_department_average_difference == Decimal("0")


def test_two_samples_use_inclusive_quartiles_and_sample_standard_deviation() -> None:
    record = BatchRecord.minimal(
        "R2",
        [sample(1, "一厂", "0.4"), sample(2, "品质", "0.6")],
    )

    result = compute_batch_statistics(record)

    assert result.sample_count == 2
    assert result.mean == Decimal("0.5")
    assert result.median == Decimal("0.5")
    assert result.first_quartile == Decimal("0.45")
    assert result.third_quartile == Decimal("0.55")
    assert result.interquartile_range == Decimal("0.10")
    assert result.standard_deviation == pytest.approx(Decimal("0.1414213562373095"))
    assert result.maximum_department_average_difference == Decimal("0.2")


def test_ten_samples_remain_decimal_and_are_not_truncated() -> None:
    values = [f"0.{index}" for index in range(1, 10)] + ["1.0"]
    record = BatchRecord.minimal(
        "R10",
        [sample(index, "品质", value) for index, value in enumerate(values, start=1)],
    )

    result = compute_batch_statistics(record)

    assert result.sample_count == 10
    assert result.mean == Decimal("0.55")
    assert result.minimum == Decimal("0.1")
    assert result.maximum == Decimal("1.0")
    assert result.median == Decimal("0.55")
    assert all(isinstance(value, Decimal) for value in result.department_averages.values())


def test_statistics_reject_record_without_usable_values() -> None:
    record = BatchRecord.minimal("EMPTY", [sample(1, "品质", None)])

    with pytest.raises(ValueError, match="usable moisture"):
        compute_batch_statistics(record)


def test_statistics_preserve_sub_float_precision_for_iqr_and_standard_deviation() -> None:
    record = BatchRecord.minimal(
        "PRECISE",
        [
            sample(1, "品质", "0.123456789012345678"),
            sample(2, "品质", "0.123456789012345679"),
            sample(3, "品质", "0.123456789012345680"),
            sample(4, "品质", "0.123456789012345681"),
        ],
    )

    result = compute_batch_statistics(record)

    assert result.interquartile_range == Decimal("1.50E-18")
    assert result.standard_deviation is not None
    assert result.standard_deviation > Decimal("1E-18")
