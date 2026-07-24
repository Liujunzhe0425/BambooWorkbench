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
    document: str


@dataclass(frozen=True, slots=True)
class AdminExperienceSummary:
    """Lightweight three-pane list entry — no body, no absolute path."""

    experience_id: str
    version: str
    status: str
    title: str
    source: str
    sha256: str
    effective_at: str
    applicable_suppliers: str
    applicable_materials: str
    applicable_seasons: str
    applicable_metrics: str
    supersedes: str


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

    # -- Three-pane projections (E-S1) --
    def list_drafts(self) -> list[AdminExperienceSummary]: ...
    def list_approved(self) -> list[AdminExperienceSummary]: ...
    def list_history(self) -> list[AdminExperienceSummary]: ...
    def copy_retired_to_draft(
        self,
        experience_id: str,
        source_version: str,
        source_expected_hash: str,
        new_version: str,
    ) -> AdminExperience: ...
