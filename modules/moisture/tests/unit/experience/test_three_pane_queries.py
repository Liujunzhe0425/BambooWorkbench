"""Unit tests for three-pane queries and history-copy (E-S1)."""

from __future__ import annotations

# ruff: noqa: E402, I001

import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.experience.local_editable_repository import (
    ExperienceAdminConflictError,
    LocalEditableExperienceRepository,
)
from moisture.application.experience_management import ExperienceManagementService

# A minimal valid experience for testing
_VALID_DOC = """---
experience_id: EXP-THREE-001
version: 1.0.0
title: Test Experience
source: internal/test-lab
status: draft
effective_at: 2026-01-01T00:00:00+00:00
applicable_suppliers:
  - 供应商甲
applicable_materials:
  - 竹丝
applicable_seasons:
  - all
applicable_metrics:
  - mean
author: 测试员
reviewer: 审核员
evidence_sources:
  - internal/synthetic-lab-001
supersedes:
---

# Test Body

This is a synthetic experience for testing.
"""


@pytest.fixture
def repo(tmp_path: Path) -> LocalEditableExperienceRepository:
    return LocalEditableExperienceRepository(tmp_path / "exp")


@pytest.fixture
def service(repo: LocalEditableExperienceRepository) -> ExperienceManagementService:
    return ExperienceManagementService(repo)


class TestThreePaneDraft:
    def test_draft_appears_in_list_drafts(
        self, repo: LocalEditableExperienceRepository,
    ) -> None:
        repo.create(_VALID_DOC)
        drafts = repo.list_drafts()
        assert len(drafts) == 1
        assert drafts[0].experience_id == "EXP-THREE-001"
        assert drafts[0].status == "draft"
        assert drafts[0].title == "Test Experience"

    def test_empty_drafts_returns_empty_list(
        self, repo: LocalEditableExperienceRepository,
    ) -> None:
        assert repo.list_drafts() == []

    def test_draft_does_not_appear_in_approved(
        self, repo: LocalEditableExperienceRepository,
    ) -> None:
        repo.create(_VALID_DOC)
        assert repo.list_approved() == []


class TestThreePaneApproved:
    @pytest.fixture(autouse=True)
    def _publish_one(self, repo: LocalEditableExperienceRepository) -> None:
        repo.create(_VALID_DOC)
        current = repo.show("EXP-THREE-001", "1.0.0")
        repo.publish("EXP-THREE-001", "1.0.0", current.sha256)

    def test_approved_appears_in_list_approved(
        self, repo: LocalEditableExperienceRepository
    ) -> None:
        approved = repo.list_approved()
        assert len(approved) == 1
        assert approved[0].status == "approved"

    def test_approved_has_summary_fields(self, repo: LocalEditableExperienceRepository) -> None:
        approved = repo.list_approved()
        entry = approved[0]
        assert entry.experience_id == "EXP-THREE-001"
        assert entry.version == "1.0.0"
        assert isinstance(entry.sha256, str)
        assert len(entry.sha256) == 64

    def test_approved_does_not_appear_in_drafts(
        self, repo: LocalEditableExperienceRepository
    ) -> None:
        assert repo.list_drafts() == []


class TestThreePaneHistory:
    @pytest.fixture(autouse=True)
    def _retire_one(self, repo: LocalEditableExperienceRepository) -> None:
        repo.create(_VALID_DOC)
        current = repo.show("EXP-THREE-001", "1.0.0")
        repo.publish("EXP-THREE-001", "1.0.0", current.sha256)
        approved = repo.show("EXP-THREE-001", "1.0.0")
        repo.retire("EXP-THREE-001", "1.0.0", approved.sha256)

    def test_retired_appears_in_list_history(self, repo: LocalEditableExperienceRepository) -> None:
        history = repo.list_history()
        assert len(history) == 1
        assert history[0].status == "retired"

    def test_retired_does_not_appear_in_approved(
        self, repo: LocalEditableExperienceRepository
    ) -> None:
        assert repo.list_approved() == []


class TestCopyRetiredToDraft:
    @pytest.fixture(autouse=True)
    def _retire_one(self, repo: LocalEditableExperienceRepository) -> None:
        repo.create(_VALID_DOC)
        current = repo.show("EXP-THREE-001", "1.0.0")
        repo.publish("EXP-THREE-001", "1.0.0", current.sha256)
        approved = repo.show("EXP-THREE-001", "1.0.0")
        repo.retire("EXP-THREE-001", "1.0.0", approved.sha256)

    def test_copy_creates_new_draft(self, repo: LocalEditableExperienceRepository) -> None:
        history = repo.list_history()
        source_hash = history[0].sha256
        result = repo.copy_retired_to_draft(
            "EXP-THREE-001", "1.0.0", source_hash, "2.0.0",
        )
        assert result.status == "draft"
        assert result.version == "2.0.0"
        assert result.experience_id == "EXP-THREE-001"

    def test_copy_preserves_title_and_source(
        self, repo: LocalEditableExperienceRepository,
    ) -> None:
        history = repo.list_history()
        drafts = repo.list_drafts()
        assert len(drafts) == 0
        repo.copy_retired_to_draft(
            "EXP-THREE-001", "1.0.0", history[0].sha256, "2.0.0",
        )
        drafts_after = repo.list_drafts()
        assert len(drafts_after) == 1
        assert "Test Experience" in drafts_after[0].title

    def test_copy_wrong_hash_raises(
        self, repo: LocalEditableExperienceRepository,
    ) -> None:
        with pytest.raises(ExperienceAdminConflictError):
            repo.copy_retired_to_draft(
                "EXP-THREE-001", "1.0.0", "a" * 64, "2.0.0",
            )

    def test_copy_to_existing_draft_raises(
        self, repo: LocalEditableExperienceRepository,
    ) -> None:
        history = repo.list_history()
        repo.copy_retired_to_draft(
            "EXP-THREE-001", "1.0.0", history[0].sha256, "2.0.0",
        )
        with pytest.raises(ExperienceAdminConflictError):
            repo.copy_retired_to_draft(
                "EXP-THREE-001", "1.0.0", history[0].sha256, "2.0.0",
            )
