"""Decimal-only batch statistics migrated from the verified legacy baseline."""

from decimal import Decimal
from statistics import median, quantiles, stdev

from moisture.domain.models import BatchRecord, BatchStatistics


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, start=Decimal("0")) / Decimal(len(values))


def compute_batch_statistics(record: BatchRecord) -> BatchStatistics:
    values = [
        sample.value_used_for_statistics
        for sample in record.samples
        if sample.value_used_for_statistics is not None
    ]
    if not values:
        raise ValueError("record has no usable moisture values")

    total_average = _mean(values)
    minimum = min(values)
    maximum = max(values)
    median_value = median(values)
    if len(values) == 1:
        first_quartile = values[0]
        third_quartile = values[0]
        standard_deviation = None
    else:
        quartile_values = quantiles(values, n=4, method="inclusive")
        first_quartile = quartile_values[0]
        third_quartile = quartile_values[2]
        standard_deviation = stdev(values)

    department_values: dict[str, list[Decimal]] = {}
    for sample in record.samples:
        value = sample.value_used_for_statistics
        if value is not None:
            department_values.setdefault(sample.department, []).append(value)
    department_averages = {
        department: _mean(department_samples)
        for department, department_samples in department_values.items()
    }
    department_average_values = list(department_averages.values())
    maximum_department_difference = (
        max(department_average_values) - min(department_average_values)
        if department_average_values
        else Decimal("0")
    )

    return BatchStatistics(
        sample_count=len(values),
        mean=total_average,
        total_average=total_average,
        standard_deviation=standard_deviation,
        minimum=minimum,
        maximum=maximum,
        range_value=maximum - minimum,
        median=median_value,
        first_quartile=first_quartile,
        third_quartile=third_quartile,
        interquartile_range=third_quartile - first_quartile,
        department_averages=department_averages,
        maximum_department_average_difference=maximum_department_difference,
    )
