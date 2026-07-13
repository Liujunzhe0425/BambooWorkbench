from pydantic import BaseModel, ConfigDict


class ConfirmationAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_id: str
    value: object
    apply_to_batch: bool = False
    remember_mapping: bool = False


class ConfirmationBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    job_id: str
    answers: list[ConfirmationAnswer]
