"""Public framework/module contract for deterministic monthly rollups."""

from pathlib import PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import ModuleId
from .result import OutputArtifact


def _absolute(path: str) -> bool:
    return PureWindowsPath(path).is_absolute()


class RollupSnapshotRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    job_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    year: int = Field(ge=2000, le=9999)
    month: int = Field(ge=1, le=12)
    path: str
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_path(self) -> "RollupSnapshotRef":
        if not _absolute(self.path):
            raise ValueError("rollup snapshot path must be absolute")
        return self


class MonthlyRollupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    transaction_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    module_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    year: int = Field(ge=2000, le=9999)
    target_month: int = Field(ge=1, le=12)
    snapshots: list[RollupSnapshotRef] = Field(min_length=1, max_length=12)
    output_dir: str
    configuration_identity: dict[str, str] = Field(default_factory=dict)
    offline_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_rollup(self) -> "MonthlyRollupRequest":
        if not _absolute(self.output_dir):
            raise ValueError("rollup output directory must be absolute")
        months = [snapshot.month for snapshot in self.snapshots]
        if months != sorted(set(months)):
            raise ValueError("rollup snapshots must be unique and ordered by month")
        if any(
            snapshot.module_id is not self.module_id
            or snapshot.year != self.year
            or snapshot.month > self.target_month
            for snapshot in self.snapshots
        ):
            raise ValueError("rollup snapshot identity is outside the requested period")
        return self


class MonthlyRollupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    transaction_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    module_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    year: int = Field(ge=2000, le=9999)
    target_month: int = Field(ge=1, le=12)
    status: Literal["success", "failed"]
    used_snapshots: dict[str, str] = Field(default_factory=dict)
    outputs: list[OutputArtifact] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status(self) -> "MonthlyRollupResult":
        if self.status == "success" and not self.outputs:
            raise ValueError("successful rollup must contain output artifacts")
        if self.status == "failed" and not self.errors:
            raise ValueError("failed rollup must explain the error")
        return self
