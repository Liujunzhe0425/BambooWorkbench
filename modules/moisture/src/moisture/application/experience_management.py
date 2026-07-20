"""Offline application service for governed experience management."""

from moisture.ports.experience_admin_repository import (
    AdminExperience,
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
