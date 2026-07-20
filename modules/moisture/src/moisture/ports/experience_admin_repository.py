"""Offline-only port for governed experience lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AdminExperience:
    experience_id: str
    version: str
    status: str
    sha256: str
    body: str
    path: str


class ExperienceAdminRepository(Protocol):
    def list(self) -> list[AdminExperience]: ...
    def show(self, experience_id: str, version: str) -> AdminExperience: ...
    def create(self, document: str) -> AdminExperience: ...
    def update(
        self, experience_id: str, version: str, document: str, expected_hash: str
    ) -> AdminExperience: ...
    def validate(self, document: str) -> AdminExperience: ...
    def publish(self, experience_id: str, version: str, expected_hash: str) -> AdminExperience: ...
    def retire(self, experience_id: str, version: str, expected_hash: str) -> AdminExperience: ...
