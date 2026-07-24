"""Offline application service for governed experience management."""

from __future__ import annotations

from moisture.ports.experience_admin_repository import (
    AdminExperience,
    AdminExperienceSummary,
    ExperienceAdminRepository,
)


class ExperienceManagementService:
    def __init__(self, repository: ExperienceAdminRepository) -> None:
        self._repository = repository

    def list(self) -> list[AdminExperience]:
        return self._repository.list()

    def show(self, experience_id: str, version: str) -> AdminExperience:
        return self._repository.show(experience_id, version)

    def create(self, document: str) -> AdminExperience:
        return self._repository.create(document)

    def update(
        self,
        experience_id: str,
        version: str,
        document: str,
        expected_hash: str,
    ) -> AdminExperience:
        return self._repository.update(experience_id, version, document, expected_hash)

    def validate(self, document: str) -> AdminExperience:
        return self._repository.validate(document)

    def publish(self, experience_id: str, version: str, expected_hash: str) -> AdminExperience:
        return self._repository.publish(experience_id, version, expected_hash)

    def retire(self, experience_id: str, version: str, expected_hash: str) -> AdminExperience:
        return self._repository.retire(experience_id, version, expected_hash)

    # -- E-S1 three-pane queries and history-copy --

    def list_drafts(self) -> list[AdminExperienceSummary]:
        return self._repository.list_drafts()

    def list_approved(self) -> list[AdminExperienceSummary]:
        return self._repository.list_approved()

    def list_history(self) -> list[AdminExperienceSummary]:
        return self._repository.list_history()

    def copy_retired_to_draft(
        self,
        experience_id: str,
        source_version: str,
        source_expected_hash: str,
        new_version: str,
    ) -> AdminExperience:
        return self._repository.copy_retired_to_draft(
            experience_id, source_version, source_expected_hash, new_version
        )
