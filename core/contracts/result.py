from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ModuleId, Severity, TaskStatus
from .service_request import ServiceRequest


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
    confidence: float = Field(ge=0, le=1)
    blocking: bool
    batch_applicable: bool
    rememberable: bool
    source: SourceRef


class OutputArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    path: str
    label: str
    mime_type: str


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
    file_results: list[FileResult] = Field(default_factory=list)
    service_requests: list[ServiceRequest] = Field(default_factory=list)
    analysis_summary: str | None = None
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
