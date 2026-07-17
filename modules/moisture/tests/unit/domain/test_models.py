import sys
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.domain.models import (  # noqa: E402
    BatchRecord,
    InputFileIdentity,
    SampleMeasurement,
)


def sample(index: int) -> SampleMeasurement:
    return SampleMeasurement(
        sample_index=index,
        department_raw="品质",
        department="品质",
        source_row=index + 3,
        initial_mass=Decimal("100"),
        dry_mass=Decimal("52"),
        foil_mass=Decimal("4"),
        source_moisture_value=Decimal("0.5"),
        verified_moisture_value=Decimal("0.5"),
        value_used_for_statistics=Decimal("0.5"),
    )


@pytest.mark.parametrize("sample_count", [1, 2, 10])
def test_batch_accepts_supported_sample_counts(sample_count: int) -> None:
    record = BatchRecord.minimal(
        f"R{sample_count}",
        [sample(index) for index in range(1, sample_count + 1)],
    )

    assert len(record.samples) == sample_count
    assert isinstance(record.samples, tuple)


def test_batch_rejects_no_samples() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        BatchRecord.minimal("R0", [])


def test_batch_rejects_more_than_ten_samples() -> None:
    with pytest.raises(ValueError, match="at most 10"):
        BatchRecord.minimal("R11", [sample(index) for index in range(1, 12)])


def test_domain_models_are_immutable() -> None:
    measurement = sample(1)
    record = BatchRecord.minimal("R1", [measurement])

    with pytest.raises(FrozenInstanceError):
        measurement.sample_index = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.record_id = "R2"  # type: ignore[misc]


def test_input_identity_preserves_path_but_fingerprint_is_explicit() -> None:
    identity = InputFileIdentity(
        source_file=Path("copy.xlsx"),
        fingerprint="a" * 64,
        input_order=2,
    )

    assert identity.source_file == Path("copy.xlsx")
    assert identity.fingerprint == "a" * 64
    assert identity.input_order == 2
