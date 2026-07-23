from enum import StrEnum
from pathlib import PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .enums import ModuleId


class ModuleManagementOperation(StrEnum):
    LIST_APPROVED_EXPERIENCES = "list_approved_experiences"
    IMPORT_HISTORY_SUMMARY = "import_history_summary"
    LIST_HISTORY_SUMMARIES = "list_history_summaries"
    RETIRE_HISTORY_SUMMARY = "retire_history_summary"


class ModuleManagementRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    operation: ModuleManagementOperation
    data_dir: str
    input_file: str | None = None
    history_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9._:-]{1,128}$")

    @model_validator(mode="after")
    def validate_operation_fields(self) -> "ModuleManagementRequest":
        if not PureWindowsPath(self.data_dir).is_absolute():
            raise ValueError("data_dir must be an absolute Windows path")
        if self.input_file is not None and not PureWindowsPath(self.input_file).is_absolute():
            raise ValueError("input_file must be an absolute Windows path")
        if self.operation is ModuleManagementOperation.IMPORT_HISTORY_SUMMARY:
            if self.input_file is None or self.history_id is not None:
                raise ValueError("import_history_summary requires only input_file")
        elif self.operation is ModuleManagementOperation.RETIRE_HISTORY_SUMMARY:
            if self.history_id is None or self.input_file is not None:
                raise ValueError("retire_history_summary requires only history_id")
        elif self.input_file is not None or self.history_id is not None:
            raise ValueError("list operations do not accept input_file or history_id")
        return self


class HistorySummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    history_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    display_name: str = Field(min_length=1, max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    date_start: str | None = None
    date_end: str | None = None
    active: bool = True

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _safe_public_text(value, "display_name")


class ApprovedExperienceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(pattern=r"^[A-Za-z0-9._:-]{1,128}$")
    title: str = Field(min_length=1, max_length=200)
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    valid_from: str | None = None
    valid_until: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _safe_public_text(value, "title")


class ModuleManagementResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    operation: ModuleManagementOperation
    status: str = Field(pattern=r"^(ok|error)$")
    history_items: list[HistorySummaryItem] = Field(default_factory=list, max_length=1000)
    experience_items: list[ApprovedExperienceItem] = Field(default_factory=list, max_length=500)
    imported_history_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._:-]{1,128}$",
    )
    error_code: str | None = Field(default=None, max_length=80)
    message: str | None = Field(default=None, max_length=300)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _safe_public_text(value, "message")

    @model_validator(mode="after")
    def validate_status_and_payload(self) -> "ModuleManagementResponse":
        if self.status == "error":
            if not self.error_code or not self.message:
                raise ValueError("error responses require error_code and message")
            if self.history_items or self.experience_items or self.imported_history_id:
                raise ValueError("error responses cannot contain success payloads")
            return self
        if self.error_code is not None:
            raise ValueError("ok responses cannot contain error_code")
        if self.operation is ModuleManagementOperation.LIST_HISTORY_SUMMARIES:
            if self.experience_items or self.imported_history_id:
                raise ValueError("history list response contains unrelated fields")
        elif self.operation is ModuleManagementOperation.LIST_APPROVED_EXPERIENCES:
            if self.history_items or self.imported_history_id:
                raise ValueError("experience list response contains unrelated fields")
        elif self.operation is ModuleManagementOperation.IMPORT_HISTORY_SUMMARY:
            if not self.imported_history_id or self.history_items or self.experience_items:
                raise ValueError("import response requires imported_history_id only")
        elif self.history_items or self.experience_items or self.imported_history_id:
            raise ValueError("retire response cannot contain list or import payloads")
        return self


def _safe_public_text(value: str, field_name: str) -> str:
    if any(character in value for character in ("\r", "\n", "\\")):
        raise ValueError(f"{field_name} must be a single public display line")
    if len(value) >= 3 and value[1:3] == ":/":
        raise ValueError(f"{field_name} must not expose an absolute path")
    return value
