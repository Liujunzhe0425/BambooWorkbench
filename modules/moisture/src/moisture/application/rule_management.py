"""Offline application service for lightweight governed rule management."""

from __future__ import annotations

from pathlib import Path

from moisture.adapters.rules.local_editable_repository import (
    LocalEditableRuleRepository,
    RuleAdminSummary,
    RulePreview,
)


class RuleManagementService:
    """Thin service boundary kept outside the formal run-module dependency graph."""

    def __init__(self, repository: LocalEditableRuleRepository) -> None:
        self._repository = repository

    def list_drafts(self) -> list[RuleAdminSummary]:
        return self._repository.list_drafts()

    def list_current(self) -> list[RuleAdminSummary]:
        return self._repository.list_current()

    def list_history(self) -> list[RuleAdminSummary]:
        return self._repository.list_history()

    def create_draft(
        self, manifest: dict[str, object], rules_yaml: str
    ) -> RuleAdminSummary:
        return self._repository.create_draft(manifest, rules_yaml)

    def update_draft(
        self,
        version: str,
        manifest: dict[str, object],
        rules_yaml: str,
        expected_package_hash: str,
    ) -> RuleAdminSummary:
        return self._repository.update_draft(
            version,
            manifest,
            rules_yaml,
            expected_package_hash,
        )

    def validate_draft(self, version: str) -> RuleAdminSummary:
        return self._repository.validate_draft(version)

    def preview_draft(
        self, version: str, summaries: tuple[Path, ...]
    ) -> RulePreview:
        return self._repository.preview_draft(version, summaries)

    def publish(
        self, version: str, expected_package_hash: str
    ) -> RuleAdminSummary:
        return self._repository.publish(version, expected_package_hash)

    def retire_current(self, expected_rules_sha256: str) -> RuleAdminSummary:
        return self._repository.retire_current(expected_rules_sha256)

    def restore(
        self, version: str, expected_rules_sha256: str
    ) -> RuleAdminSummary:
        return self._repository.restore(version, expected_rules_sha256)

    def copy_history_to_draft(
        self,
        source_version: str,
        source_expected_hash: str,
        new_version: str,
    ) -> RuleAdminSummary:
        return self._repository.copy_history_to_draft(
            source_version,
            source_expected_hash,
            new_version,
        )
