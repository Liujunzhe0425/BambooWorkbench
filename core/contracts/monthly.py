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


class RollupOutputArtifact(OutputArtifact):
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RollupSnapshotHash(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    month: int = Field(ge=1, le=12)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MonthlyRollupError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    message: str = Field(min_length=1, max_length=300)


class RollupConfigurationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class MonthlyRollupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    transaction_id: str = Field(pattern=r"^[A-Za-z0-9-]{6,64}$")
    module_id: ModuleId
    module_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    year: int = Field(ge=2000, le=9999)
    target_month: int = Field(ge=1, le=12)
    snapshots: list[RollupSnapshotRef] = Field(min_length=1, max_length=12)
    snapshot_root: str
    output_dir: str
    configuration_identity: RollupConfigurationIdentity | None = None
    offline_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_rollup(self) -> "MonthlyRollupRequest":
        if not _absolute(self.output_dir) or not _absolute(self.snapshot_root):
            raise ValueError("rollup snapshot and output directories must be absolute")
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
        snapshot_root = PureWindowsPath(self.snapshot_root)
        if any(
            not PureWindowsPath(snapshot.path).is_relative_to(snapshot_root)
            for snapshot in self.snapshots
        ):
            raise ValueError("rollup snapshots must be contained in snapshot_root")
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
    used_months: list[int] = Field(default_factory=list, max_length=12)
    snapshot_hashes: list[RollupSnapshotHash] = Field(default_factory=list, max_length=12)
    record_count: int = Field(default=0, ge=0)
    outputs: list[RollupOutputArtifact] = Field(default_factory=list)
    network_call_count: Literal[0] = 0
    error: MonthlyRollupError | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "MonthlyRollupResult":
        if self.status == "success" and not self.outputs:
            raise ValueError("successful rollup must contain output artifacts")
        if self.status == "success" and self.error is not None:
            raise ValueError("successful rollup cannot contain an error")
        if self.status == "failed" and self.error is None:
            raise ValueError("failed rollup must contain a stable error")
        if self.status == "failed" and self.outputs:
            raise ValueError("failed rollup cannot publish output artifacts")
        if self.used_months != sorted(set(self.used_months)):
            raise ValueError("used months must be unique and ordered")
        hash_months = [item.month for item in self.snapshot_hashes]
        hash_ids = [item.snapshot_id for item in self.snapshot_hashes]
        if hash_months != sorted(set(hash_months)) or len(hash_ids) != len(set(hash_ids)):
            raise ValueError("snapshot hash acknowledgements must be unique and ordered")
        return self
