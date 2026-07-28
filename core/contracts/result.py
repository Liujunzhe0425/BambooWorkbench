import re
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ModuleId, Severity, TaskStatus
from .service_request import ServiceRequest

_SENSITIVE_LEARNING_KEY = re.compile(
    r"(?:customer|client|name|address|phone|email|path|file|raw|text|客户|姓名|地址|电话)",
    re.IGNORECASE,
)


class LearningCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    label: str = Field(min_length=1, max_length=160)


class LearningDescriptor(BaseModel):
    """Module-owned, structured and redacted preference-learning description."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    learning_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    field: str = Field(min_length=1, max_length=120)
    context: dict[str, str | int | float | bool | None]
    context_levels: list[list[str]] = Field(min_length=1, max_length=8)
    candidates: list[LearningCandidate] = Field(min_length=1, max_length=64)
    base_suggestion_id: str
    preference_adjustable: bool = True

    @model_validator(mode="after")
    def validate_learning_shape(self) -> "LearningDescriptor":
        context_keys = set(self.context)
        if not context_keys or any(not key or len(key) > 80 for key in context_keys):
            raise ValueError("learning context keys must be stable non-empty identifiers")
        if any(_SENSITIVE_LEARNING_KEY.search(key) for key in context_keys):
            raise ValueError("learning context contains a forbidden sensitive field")
        for value in self.context.values():
            if isinstance(value, str) and (
                len(value) > 120 or PureWindowsPath(value).is_absolute()
            ):
                raise ValueError("learning context values must be short redacted categories")
        if any(not level or not set(level) <= context_keys for level in self.context_levels):
            raise ValueError("learning context levels must reference context fields")
        normalized = [tuple(level) for level in self.context_levels]
        if len(normalized) != len(set(normalized)):
            raise ValueError("learning context levels must be unique")
        if any(
            set(right) >= set(left)
            for left, right in zip(normalized, normalized[1:], strict=False)
        ):
            raise ValueError("learning context levels must become progressively broader")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("learning candidate IDs must be unique")
        if self.base_suggestion_id not in candidate_ids:
            raise ValueError("base suggestion must be a declared candidate")
        return self


class ResultSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_count: int = Field(ge=0)
    processed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    anomaly_count: int = Field(ge=0)
    confirmation_count: int = Field(ge=0)


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file: str
    sheet: str | None = None
    cell_or_range: str | None = None


class Anomaly(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anomaly_id: str
    severity: Severity
    field: str
    value: object | None = None
    rule_id: str | None = None
    message: str
    suggestion: str | None = None
    source: SourceRef


class ConfirmationPrompt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: str
    field: str
    reason: str
    suggested_value: object | None = None
    options: list[object] = Field(default_factory=list)
    value_type: Literal["text", "date", "number"] = "text"
    confidence: float = Field(ge=0, le=1)
    blocking: bool
    batch_applicable: bool
    rememberable: bool
    source: SourceRef
    learning: LearningDescriptor | None = None


class OutputArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    path: str
    label: str
    mime_type: str


class MonthlySnapshotArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    path: str
    snapshot_format: str = Field(min_length=1, max_length=80)
    year: int = Field(ge=2000, le=9999)
    month: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def validate_path(self) -> "MonthlySnapshotArtifact":
        if not PureWindowsPath(self.path).is_absolute():
            raise ValueError("monthly snapshot path must be absolute")
        return self


class FileResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_file: str
    fingerprint: str
    status: TaskStatus
    extracted_records: int = Field(ge=0)
    missing_fields: list[str] = Field(default_factory=list)
    anomaly_count: int = Field(ge=0)
    error: str | None = None


class ModuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    job_id: str
    module_id: ModuleId
    module_version: str
    status: TaskStatus
    rule_version: str | None = None
    summary: ResultSummary
    anomalies: list[Anomaly] = Field(default_factory=list)
    confirmations: list[ConfirmationPrompt] = Field(default_factory=list)
    outputs: list[OutputArtifact] = Field(default_factory=list)
    monthly_snapshot: MonthlySnapshotArtifact | None = None
    file_results: list[FileResult] = Field(default_factory=list)
    service_requests: list[ServiceRequest] = Field(default_factory=list)
    analysis_summary: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime

    @model_validator(mode="after")
    def validate_confirmation_state(self) -> "ModuleResult":
        if self.status is TaskStatus.NEEDS_CONFIRMATION and not self.confirmations:
            raise ValueError("needs_confirmation requires at least one prompt")
        if self.summary.confirmation_count != len(self.confirmations):
            raise ValueError("confirmation_count must equal confirmation list length")
        return self
