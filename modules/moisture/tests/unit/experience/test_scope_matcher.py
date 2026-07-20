import sys
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.scope_matcher import (  # noqa: E402
    match_experience_scope,
)
from moisture.domain.models import BatchRecord, SampleMeasurement  # noqa: E402
from moisture.ports.experience_repository import (  # noqa: E402
    ExperienceMetadata,
    ExperienceQuery,
)


def _metadata(**updates: object) -> ExperienceMetadata:
    values: dict[str, object] = {
        "experience_id": "EXP-001",
        "version": "1.0.0",
        "status": "approved",
        "title": "竹丝季节复核指导",
        "source": "internal-review/EXP-001",
        "applicable_suppliers": ("示例供应方",),
        "applicable_materials": ("原竹丝",),
        "applicable_seasons": ("spring",),
        "applicable_metrics": ("total_average",),
        "author": "author-a",
        "reviewer": "reviewer-b",
        "evidence_sources": ("internal-evidence/EXP-001",),
        "effective_at": datetime(2026, 1, 1, tzinfo=UTC),
        "supersedes": None,
    }
    values.update(updates)
    return ExperienceMetadata(**values)  # type: ignore[arg-type]


def test_scope_matching_normalizes_nfkc_whitespace_and_case() -> None:
    query = ExperienceQuery(
        supplier="  示例供应方 ",
        material="原竹丝",
        season="SPRING",
        metric="ＴＯＴＡＬ＿ＡＶＥＲＡＧＥ",
    )

    match = match_experience_scope(_metadata(), query)

    assert match is not None
    assert match.exact_match_count == 4
    assert match.reasons == (
        "supplier:exact",
        "material:exact",
        "season:exact",
        "metric:exact",
    )


def test_wildcard_matches_but_ranks_below_exact_scope() -> None:
    query = ExperienceQuery(
        supplier="示例供应方",
        material="原竹丝",
        season="spring",
        metric="total_average",
    )

    exact = match_experience_scope(_metadata(), query)
    wildcard = match_experience_scope(
        _metadata(
            experience_id="EXP-ALL",
            applicable_suppliers=("*",),
            applicable_materials=("*",),
            applicable_seasons=("*",),
            applicable_metrics=("*",),
        ),
        query,
    )

    assert exact is not None and wildcard is not None
    assert exact.exact_match_count > wildcard.exact_match_count
    assert wildcard.reasons == (
        "supplier:wildcard",
        "material:wildcard",
        "season:wildcard",
        "metric:wildcard",
    )


def test_wildcard_dominates_mixed_scope_dimension() -> None:
    query = ExperienceQuery(
        supplier="示例供应方",
        material="原竹丝",
        season="spring",
        metric="total_average",
    )

    match = match_experience_scope(
        _metadata(applicable_suppliers=("*", "示例供应方")), query
    )

    assert match is not None
    assert match.exact_match_count == 3
    assert match.reasons[0] == "supplier:wildcard"


def test_scope_mismatch_returns_none() -> None:
    query = ExperienceQuery(
        supplier="其他供应方",
        material="原竹丝",
        season="spring",
        metric="total_average",
    )
    assert match_experience_scope(_metadata(), query) is None


def test_query_from_batch_record_derives_season() -> None:
    record = BatchRecord(
        record_id="R1",
        supplier="示例供应方",
        material_type="原竹丝",
        arrival_date=date(2026, 7, 14),
        samples=(
            SampleMeasurement(
                sample_index=1,
                department_raw="示例部门",
                department="示例部门",
                source_row=5,
                initial_mass=Decimal("100"),
                dry_mass=Decimal("52"),
                foil_mass=Decimal("4"),
                source_moisture_value=Decimal("0.60"),
                verified_moisture_value=Decimal("0.60"),
                value_used_for_statistics=Decimal("0.60"),
            ),
        ),
    )

    query = ExperienceQuery.from_record(record, "total_average")

    assert query.supplier == "示例供应方"
    assert query.material == "原竹丝"
    assert query.season == "summer"
