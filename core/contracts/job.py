from pathlib import PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import JobPhase, ModuleId, RunMode


def _is_absolute(path: str) -> bool:
    return PureWindowsPath(path).is_absolute()


class JobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    phase: JobPhase
    run_mode: RunMode
    input_files: list[str] = Field(min_length=1)
    output_dir: str
    module_config_file: str | None = None
    ai_enabled: bool = False
    allowed_knowledge_scopes: list[str] = Field(default_factory=list)
    parent_job_id: str | None = None
    confirmation_file: str | None = None
    service_response_file: str | None = None
    task_name: str | None = Field(default=None, min_length=1, max_length=160)
    period_year: int | None = Field(default=None, ge=2000, le=9999)
    period_month: int | None = Field(default=None, ge=1, le=12)
    learning_enabled: bool = True

    @model_validator(mode="after")
    def validate_paths_and_phase(self) -> "JobRequest":
        paths = [*self.input_files, self.output_dir]
        optional_paths = [
            self.module_config_file,
            self.confirmation_file,
            self.service_response_file,
        ]
        paths.extend(path for path in optional_paths if path is not None)
        if not all(_is_absolute(path) for path in paths):
            raise ValueError("all job paths must be absolute Windows paths")
        if self.phase is JobPhase.FINALIZE and (
            not self.parent_job_id or not self.confirmation_file
        ):
            raise ValueError("finalize jobs require parent_job_id and confirmation_file")
        if (self.period_year is None) != (self.period_month is None):
            raise ValueError("task period year and month must be supplied together")
        return self
