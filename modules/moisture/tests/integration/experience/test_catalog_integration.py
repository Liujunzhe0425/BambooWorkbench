"""Integration tests for approved experience catalog using desensitized fixtures."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.catalog import (  # noqa: E402
    build_approved_catalog,
)

FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "desensitized"


class TestCatalogWithDesensitizedFixtures:
    """Verify catalog builder against the synthetic approved-experience fixture."""

    @pytest.fixture(autouse=False)
    def experience_root(self) -> Path:
        root = FIXTURES / "approved_experiences"
        if not (root / "manifest.json").is_file():
            pytest.skip("desensitized fixture not available")
        return root

    def test_catalog_loads_desensitized_approved_experiences(
        self, experience_root: Path
    ) -> None:
        catalog = build_approved_catalog(experience_root, as_of=date(2026, 7, 23))

        assert catalog["schema_version"] == "1.0"
        assert isinstance(catalog["entries"], list)
        assert len(catalog["entries"]) >= 1

        entry_ids = sorted(e["entry_id"] for e in catalog["entries"])
        assert "EXP-SYN-001" in entry_ids
        assert "EXP-SYN-002" in entry_ids

    def test_each_entry_has_catalog_schema_fields(
        self, experience_root: Path
    ) -> None:
        catalog = build_approved_catalog(experience_root, as_of=date(2026, 7, 23))

        for entry in catalog["entries"]:
            assert "entry_id" in entry
            assert "title" in entry
            assert "version" in entry
            assert "scope" in entry
            assert "effective_from" in entry
            assert "effective_to" in entry
            assert "sha256" in entry
            assert len(entry["sha256"]) == 64

    def test_catalog_is_json_serializable(self, experience_root: Path) -> None:
        catalog = build_approved_catalog(experience_root, as_of=date(2026, 7, 23))

        serialized = json.dumps(catalog, ensure_ascii=False)
        deserialized = json.loads(serialized)

        assert deserialized == catalog

    def test_entry_scope_contains_applicable_dimensions(
        self, experience_root: Path
    ) -> None:
        catalog = build_approved_catalog(experience_root, as_of=date(2026, 7, 23))

        for entry in catalog["entries"]:
            assert "suppliers:" in entry["scope"]
            assert "materials:" in entry["scope"]
            assert "seasons:" in entry["scope"]
            assert "metrics:" in entry["scope"]

    def test_effective_from_is_a_valid_date_string(
        self, experience_root: Path
    ) -> None:
        catalog = build_approved_catalog(experience_root, as_of=date(2026, 7, 23))

        for entry in catalog["entries"]:
            from datetime import datetime as dt
            dt.fromisoformat(entry["effective_from"])

    def test_all_entries_are_within_effective_period(
        self, experience_root: Path
    ) -> None:
        catalog = build_approved_catalog(experience_root, as_of=date(2026, 7, 23))

        today = date(2026, 7, 23)
        for entry in catalog["entries"]:
            effective_from = date.fromisoformat(entry["effective_from"])
            assert effective_from <= today
            if entry["effective_to"] is not None:
                effective_to = date.fromisoformat(entry["effective_to"])
                assert effective_to >= today

    def test_desensitized_fixture_has_no_real_data(self) -> None:
        """Ensure fixture files do not contain real identifiers or secrets."""
        fixture_files = list((FIXTURES / "approved_experiences").rglob("*.md"))
        fixture_files.append(FIXTURES / "summary_current.json")
        fixture_files.append(FIXTURES / "summary_history.json")

        forbidden = ["API_KEY", "api-key", "secret", "password", "token"]
        for fpath in fixture_files:
            if not fpath.is_file():
                continue
            text = fpath.read_text(encoding="utf-8").lower()
            for keyword in forbidden:
                assert keyword not in text, f"{fpath.name} contains forbidden keyword: {keyword}"
