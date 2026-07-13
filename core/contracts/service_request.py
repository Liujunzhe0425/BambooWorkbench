from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ServiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    service: Literal["knowledge", "ai"]
    scope: str | None = None
    purpose: str = Field(min_length=1, max_length=300)
    payload: dict[str, object]
    requires_user_consent: bool = True
