from pydantic import BaseModel, ConfigDict, Field

from .enums import ModuleId


class ModuleManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    module_id: ModuleId
    module_name: str = Field(min_length=1, max_length=80)
    module_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    entrypoint: str = Field(min_length=1)
    management_entrypoint: str | None = Field(default=None, min_length=1)
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    supported_extensions: list[str] = Field(min_length=1)
    supports_single_file: bool
    supports_batch: bool
    supports_incremental: bool
    requires_network: bool
