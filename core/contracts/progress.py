from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProgressEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["progress"]
    percent: int = Field(ge=0, le=100)
    message: str = Field(min_length=1, max_length=300)
    source_file: str | None = None
