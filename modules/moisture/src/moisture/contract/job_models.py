"""Immutable boundary model for the official JobRequest contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PureWindowsPath
from typing import Any


class ModuleId(StrEnum):
    MOISTURE = "moisture"
    BOILING = "boiling"
    AFTER_SALES = "after_sales"


class JobPhase(StrEnum):
    DRAFT = "draft"
    FINALIZE = "finalize"


class RunMode(StrEnum):
    SINGLE = "single"
    BATCH = "batch"
    INCREMENTAL = "incremental"


class JobModelError(ValueError):
    def __init__(self, code: str, field: str, message: str) -> None:
        self.code = code
        self.field = field
        super().__init__(message)


def _path(value: str, field: str) -> Path:
    if not PureWindowsPath(value).is_absolute():
        raise JobModelError("CONTRACT_SEMANTIC_INVALID", field, "path must be absolute")
    return Path(value)


@dataclass(frozen=True, slots=True)
class JobRequest:
    schema_version: str
    job_id: str
    module_id: ModuleId
    phase: JobPhase
    run_mode: RunMode
    input_files: tuple[Path, ...]
    output_dir: Path
    module_config_file: Path | None = None
    ai_enabled: bool = False
    allowed_knowledge_scopes: tuple[str, ...] = ()
    parent_job_id: str | None = None
    confirmation_file: Path | None = None
    service_response_file: Path | None = None
    task_name: str | None = None
    period_year: int | None = None
    period_month: int | None = None
    learning_enabled: bool = True

    @property
    def root_job_id(self) -> str:
        if self.phase is JobPhase.FINALIZE:
            if self.parent_job_id is None:  # guarded during construction
                raise JobModelError(
                    "CONTRACT_SEMANTIC_INVALID",
                    "parent_job_id",
                    "finalize job has no parent identity",
                )
            return self.parent_job_id
        return self.job_id

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> JobRequest:
        module_id = ModuleId(payload["module_id"])
        if module_id is not ModuleId.MOISTURE:
            raise JobModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "module_id",
                "job is intended for a different module",
            )
        phase = JobPhase(payload["phase"])
        parent_job_id = payload.get("parent_job_id")
        confirmation_value = payload.get("confirmation_file")
        if phase is JobPhase.FINALIZE and not parent_job_id:
            raise JobModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "parent_job_id",
                "finalize jobs require parent identity",
            )
        period_year = payload.get("period_year")
        period_month = payload.get("period_month")
        if (period_year is None) != (period_month is None):
            raise JobModelError(
                "CONTRACT_SEMANTIC_INVALID",
                "period_year",
                "task period year and month must be supplied together",
            )

        return cls(
            schema_version=payload["schema_version"],
            job_id=payload["job_id"],
            module_id=module_id,
            phase=phase,
            run_mode=RunMode(payload["run_mode"]),
            input_files=tuple(
                _path(value, f"input_files.{index}")
                for index, value in enumerate(payload["input_files"])
            ),
            output_dir=_path(payload["output_dir"], "output_dir"),
            module_config_file=(
                _path(payload["module_config_file"], "module_config_file")
                if payload.get("module_config_file") is not None
                else None
            ),
            ai_enabled=payload.get("ai_enabled", False),
            allowed_knowledge_scopes=tuple(payload.get("allowed_knowledge_scopes", [])),
            parent_job_id=parent_job_id,
            confirmation_file=(
                _path(confirmation_value, "confirmation_file")
                if confirmation_value is not None
                else None
            ),
            service_response_file=(
                _path(payload["service_response_file"], "service_response_file")
                if payload.get("service_response_file") is not None
                else None
            ),
            task_name=payload.get("task_name"),
            period_year=period_year,
            period_month=period_month,
            learning_enabled=payload.get("learning_enabled", True),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "module_id": self.module_id.value,
            "phase": self.phase.value,
            "run_mode": self.run_mode.value,
            "input_files": [str(path) for path in self.input_files],
            "output_dir": str(self.output_dir),
            "module_config_file": (
                str(self.module_config_file) if self.module_config_file else None
            ),
            "ai_enabled": self.ai_enabled,
            "allowed_knowledge_scopes": list(self.allowed_knowledge_scopes),
            "parent_job_id": self.parent_job_id,
            "confirmation_file": (str(self.confirmation_file) if self.confirmation_file else None),
            "service_response_file": (
                str(self.service_response_file) if self.service_response_file else None
            ),
            "task_name": self.task_name,
            "period_year": self.period_year,
            "period_month": self.period_month,
            "learning_enabled": self.learning_enabled,
        }
