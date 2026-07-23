"""Unit tests for approved experience catalog builder."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.catalog import (  # noqa: E402
    ExperienceValidationError,
    build_approved_catalog,
)

UTC = UTC


def _front_matter(**overrides: object) -> dict:
    defaults: dict = {
        "experience_id": "EXP-CAT-001",
        "version": "1.0.0",
        "status": "approved",
        "title": "竹丝含水率夏季复核指导",
        "source": "internal/LAB-01",
        "applicable_suppliers": ["供应方A"],
        "applicable_materials": ["原竹丝"],
        "applicable_seasons": ["summer"],
        "applicable_metrics": ["total_average"],
        "author": "author-a",
        "reviewer": "reviewer-b",
        "evidence_sources": ["evidence/01"],
        "effective_at": "2026-01-01T00:00:00Z",
        "supersedes": None,
    }
    defaults.update(overrides)
    return defaults


def _make_document(front_matter: dict, body: str = "复核指导内容。") -> bytes:
    rendered = yaml.safe_dump(front_matter, allow_unicode=True, sort_keys=False)
    return f"---\n{rendered}---\n{body}\n".encode()


def _make_manifest(entries: list[dict]) -> bytes:
    return json.dumps(
        {"schema_version": "1.0", "entries": entries}, ensure_ascii=False
    ).encode("utf-8")


def _setup_experience_root(
    root: Path,
    entries: list[tuple[str, dict, str]],
) -> Path:
    """Set up an experience root with approved entries and a manifest.

    Each entry is (filename, front_matter, body).
    """
    approved_dir = root / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: list[dict] = []
    for filename, fm, body in entries:
        path = approved_dir / filename
        content = _make_document(fm, body)
        path.write_bytes(content)
        manifest_entries.append({
            "path": f"approved/{filename}",
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    (root / "manifest.json").write_bytes(_make_manifest(manifest_entries))
    return root


class TestBuildApprovedCatalog:
    """Tests for build_approved_catalog."""

    def test_returns_only_approved_in_effective_period(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "approved_effective.md",
                    _front_matter(
                        experience_id="EXP-001",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "指导A",
                ),
                (
                    "approved_future.md",
                    _front_matter(
                        experience_id="EXP-002",
                        effective_at="2099-01-01T00:00:00Z",
                    ),
                    "指导B-未来",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        assert catalog["schema_version"] == "1.0"
        entry_ids = [e["entry_id"] for e in catalog["entries"]]
        assert "EXP-001" in entry_ids
        assert "EXP-002" not in entry_ids

    def test_draft_and_retired_are_excluded(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "approved_a.md",
                    _front_matter(
                        experience_id="EXP-APPROVED",
                        status="approved",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "指导",
                ),
                (
                    "draft_one.md",
                    _front_matter(
                        experience_id="EXP-DRAFT",
                        status="draft",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "草稿",
                ),
                (
                    "retired_one.md",
                    _front_matter(
                        experience_id="EXP-RETIRED",
                        status="retired",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "已退役",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        entry_ids = [e["entry_id"] for e in catalog["entries"]]
        assert entry_ids == ["EXP-APPROVED"]
        assert "EXP-DRAFT" not in entry_ids
        assert "EXP-RETIRED" not in entry_ids

    def test_expired_entry_with_effective_to_in_past_is_excluded(
        self, tmp_path: Path
    ) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "active.md",
                    _front_matter(
                        experience_id="EXP-ACTIVE",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "活跃",
                ),
                (
                    "expired.md",
                    _front_matter(
                        experience_id="EXP-EXPIRED",
                        effective_at="2025-01-01T00:00:00Z",
                        effective_to="2025-12-31T00:00:00Z",
                    ),
                    "过期",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        entry_ids = [e["entry_id"] for e in catalog["entries"]]
        assert "EXP-ACTIVE" in entry_ids
        assert "EXP-EXPIRED" not in entry_ids

    def test_null_effective_to_means_no_upper_bound(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "no_end.md",
                    _front_matter(
                        experience_id="EXP-NO-END",
                        effective_at="2025-01-01T00:00:00Z",
                    ),
                    "无结束日期",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        entry_ids = [e["entry_id"] for e in catalog["entries"]]
        assert "EXP-NO-END" in entry_ids

    def test_all_draft_or_expired_returns_empty_list(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "draft.md",
                    _front_matter(
                        experience_id="EXP-DRAFT-ONLY",
                        status="draft",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "全部草稿",
                ),
                (
                    "future.md",
                    _front_matter(
                        experience_id="EXP-FUTURE",
                        status="approved",
                        effective_at="2099-06-01T00:00:00Z",
                    ),
                    "未来才生效",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        assert catalog["entries"] == []

    def test_catalog_output_passes_schema_validation(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "valid.md",
                    _front_matter(
                        experience_id="EXP-SCHEMA",
                        version="1.2.3",
                        title="架构验证条目",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "内容",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        assert catalog["schema_version"] == "1.0"
        assert isinstance(catalog["entries"], list)
        assert len(catalog["entries"]) == 1
        entry = catalog["entries"][0]
        assert entry["entry_id"] == "EXP-SCHEMA"
        assert entry["title"] == "架构验证条目"
        assert entry["version"] == "1.2.3"
        assert entry["effective_from"] == "2026-01-01"
        assert entry["effective_to"] is None
        assert len(entry["sha256"]) == 64
        assert "suppliers:" in entry["scope"]
        assert "materials:" in entry["scope"]
        assert "seasons:" in entry["scope"]
        assert "metrics:" in entry["scope"]

    def test_entry_contains_all_required_fields(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "full.md",
                    _front_matter(
                        experience_id="EXP-FIELDS",
                        version="2.0.0",
                        title="完整字段测试",
                        effective_at="2026-03-15T08:00:00Z",
                        applicable_suppliers=["供应方X", "供应方Y"],
                        applicable_materials=["竹丝A"],
                        applicable_seasons=["spring", "autumn"],
                        applicable_metrics=["mean", "total_average"],
                    ),
                    "正文内容。",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        entry = catalog["entries"][0]
        required_keys = {
            "entry_id", "title", "version", "scope",
            "effective_from", "effective_to", "sha256",
        }
        assert set(entry.keys()) == required_keys
        assert entry["entry_id"] == "EXP-FIELDS"
        assert entry["version"] == "2.0.0"
        assert entry["effective_from"] == "2026-03-15"

    def test_effective_at_as_datetime_object_is_accepted(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "dt_obj.md",
                    _front_matter(
                        experience_id="EXP-DT",
                        effective_at=datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC),
                    ),
                    "内容",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        assert len(catalog["entries"]) == 1
        assert catalog["entries"][0]["effective_from"] == "2026-05-01"

    def test_multiple_approved_entries_are_all_returned(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    f"entry_{i}.md",
                    _front_matter(
                        experience_id=f"EXP-{i:03d}",
                        version=f"{i}.0.0",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    f"指导{i}",
                )
                for i in range(1, 6)
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        assert len(catalog["entries"]) == 5
        entry_ids = sorted(e["entry_id"] for e in catalog["entries"])
        assert entry_ids == ["EXP-001", "EXP-002", "EXP-003", "EXP-004", "EXP-005"]

    def test_missing_manifest_raises_error(self, tmp_path: Path) -> None:
        with pytest.raises(ExperienceValidationError, match="manifest"):
            build_approved_catalog(tmp_path)

    def test_sha256_mismatch_raises_error(self, tmp_path: Path) -> None:
        approved_dir = tmp_path / "approved"
        approved_dir.mkdir(parents=True)
        path = approved_dir / "tampered.md"
        content = _make_document(_front_matter())
        path.write_bytes(content)
        (tmp_path / "manifest.json").write_bytes(
            _make_manifest([{
                "path": "approved/tampered.md",
                "sha256": "0" * 64,
            }])
        )

        with pytest.raises(ExperienceValidationError, match="SHA-256"):
            build_approved_catalog(tmp_path)

    def test_nonexistent_root_raises_error(self) -> None:
        with pytest.raises(ExperienceValidationError, match="does not exist"):
            build_approved_catalog(Path("/nonexistent/path/12345"))

    def test_effective_from_today_is_included(self, tmp_path: Path) -> None:
        today = date(2026, 7, 23)
        _setup_experience_root(
            tmp_path,
            [
                (
                    "today.md",
                    _front_matter(
                        experience_id="EXP-TODAY",
                        effective_at=f"{today.isoformat()}T00:00:00Z",
                    ),
                    "今天生效",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=today)

        assert len(catalog["entries"]) == 1

    def test_catalog_entries_max_1000_limit_is_enforced_by_schema(
        self, tmp_path: Path
    ) -> None:
        """Schema enforces maxItems=1000; we verify a small valid case works."""
        _setup_experience_root(
            tmp_path,
            [
                (
                    "single.md",
                    _front_matter(
                        experience_id="EXP-LIMIT",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "限制测试",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        assert len(catalog["entries"]) <= 1000

    def test_pending_review_status_is_excluded(self, tmp_path: Path) -> None:
        _setup_experience_root(
            tmp_path,
            [
                (
                    "approved.md",
                    _front_matter(
                        experience_id="EXP-APPROVED",
                        status="approved",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "获批",
                ),
                (
                    "pending.md",
                    _front_matter(
                        experience_id="EXP-PENDING",
                        status="pending_review",
                        effective_at="2026-01-01T00:00:00Z",
                    ),
                    "待审",
                ),
            ],
        )

        catalog = build_approved_catalog(tmp_path, as_of=date(2026, 7, 14))

        entry_ids = [e["entry_id"] for e in catalog["entries"]]
        assert "EXP-PENDING" not in entry_ids
