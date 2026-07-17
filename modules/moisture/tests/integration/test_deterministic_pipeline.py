from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.deterministic_pipeline import DeterministicPipeline  # noqa: E402
from moisture.ports.experience_repository import ExperienceReference  # noqa: E402

pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def test_single_file_runs_formula_statistics_and_approved_rules(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(
        tmp_path / "source.xlsx", departments={"品质": 2}, moisture_values=(0.60, 0.61)
    )

    outcome = DeterministicPipeline().run((source,))

    assert outcome.processed_count == 1
    assert outcome.failed_count == 0
    assert outcome.skipped_count == 0
    assert outcome.batches[0].statistics.sample_count == 2
    assert outcome.batches[0].final_display_color.value == "orange"
    assert outcome.batches[0].screening_decision.status.value == "high"
    assert outcome.pending_rule_matches == ()


class _ExperienceRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.query = None

    def search(self, query):
        self.query = query
        if self.fail:
            raise OSError("offline store unavailable")
        return [
            ExperienceReference(
                experience_id="EXP-TEST-001",
                version="1.0.0",
                status="approved",
                title="脱敏复核经验",
                source="test-governance",
                applicable_suppliers=("*",),
                applicable_materials=("*",),
                applicable_seasons=("*",),
                applicable_metrics=("total_average",),
                author="author",
                reviewer="reviewer",
                evidence_sources=("test-evidence",),
                effective_at=datetime(2026, 1, 1, tzinfo=UTC),
                supersedes=None,
                quoted_reference="仅用于复核提示",
                content_hash="a" * 64,
                reference_path="approved/EXP-TEST-001--1.0.0.md",
            )
        ]

    def get(self, experience_id, version):
        return None


def test_pipeline_cites_only_read_only_repository_results(tmp_path: Path, workbook_factory) -> None:
    source = workbook_factory(tmp_path / "source.xlsx", departments={"品质": 2})
    repository = _ExperienceRepository()

    outcome = DeterministicPipeline(experience_repository=repository).run((source,))

    assert repository.query.metric == "total_average"
    assert outcome.batches[0].experience_references[0].entry_id == "EXP-TEST-001"
    assert "EXPERIENCE_GUIDANCE_DEGRADED" not in outcome.errors


def test_experience_failure_does_not_break_deterministic_result(
    tmp_path: Path, workbook_factory
) -> None:
    source = workbook_factory(tmp_path / "source.xlsx", departments={"品质": 2})

    outcome = DeterministicPipeline(
        experience_repository=_ExperienceRepository(fail=True)
    ).run((source,))

    assert outcome.processed_count == 1
    assert outcome.batches[0].experience_references == ()
    assert "EXPERIENCE_GUIDANCE_DEGRADED" in outcome.errors
