from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .enums import ModuleId


class ModuleManagementContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.\d+$")
    request_schema: str = Field(min_length=1, max_length=240)
    response_schema: str = Field(min_length=1, max_length=240)


class FrameworkAIRequirement(BaseModel):
    """Framework-hosted AI policy; it never grants network access to the module process."""

    model_config = ConfigDict(extra="forbid")

    required: bool = True
    setup_page: Literal["module"] = "module"
    service_before_confirmation: bool = True


class MonthlyRollupContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    entrypoint: str = Field(min_length=1, max_length=240)
    snapshot_schema: str = Field(min_length=1, max_length=240)
    request_schema: str = Field(min_length=1, max_length=240)
    response_schema: str = Field(min_length=1, max_length=240)


class ModuleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    module_id: ModuleId
    module_name: str = Field(min_length=1, max_length=80)
    module_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    entrypoint: str = Field(min_length=1)
    management_entrypoint: str | None = Field(default=None, min_length=1)
    management_contract: ModuleManagementContract | None = None
    framework_ai: FrameworkAIRequirement | None = None
    monthly_rollup: MonthlyRollupContract | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    supported_extensions: list[str] = Field(min_length=1)
    supports_single_file: bool
    supports_batch: bool
    supports_incremental: bool
    requires_network: bool
