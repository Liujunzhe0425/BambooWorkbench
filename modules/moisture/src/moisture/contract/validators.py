"""Schema-first validation for the module's external contract payloads."""

from __future__ import annotations

from collections.abc import Mapping

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from moisture.contract.job_models import JobModelError, JobRequest
from moisture.contract.result_models import ModuleResult, ResultModelError
from moisture.contract.schema_lock import SchemaBundleError, load_bundled_schema


class ContractValidationError(ValueError):
    """Stable module-owned error for invalid external contract data."""

    def __init__(self, code: str, field: str, message: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} at {field}: {message}")


def _field_path(error: ValidationError) -> str:
    path = ".".join(str(part) for part in error.absolute_path)
    if error.validator == "required" and isinstance(error.validator_value, list):
        missing = [key for key in error.validator_value if key not in error.instance]
        if missing:
            path = ".".join(part for part in (path, missing[0]) if part)
    if error.validator == "additionalProperties":
        unexpected = sorted(set(error.instance) - set(error.schema.get("properties", {})))
        if unexpected:
            path = ".".join(part for part in (path, unexpected[0]) if part)
    return path or "$"


def _validate_with_schema(name: str, payload: object) -> None:
    try:
        schema = load_bundled_schema(name)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        error = next(iter(validator.iter_errors(payload)), None)
    except (SchemaBundleError, SchemaError) as failure:
        raise ContractValidationError(
            "CONTRACT_SCHEMA_UNAVAILABLE", "$", "bundled contract schema is unavailable"
        ) from failure
    if error is not None:
        raise ContractValidationError(
            "CONTRACT_SCHEMA_INVALID", _field_path(error), "payload violates contract"
        ) from None

def validate_job_payload(payload: object) -> JobRequest:
    _validate_with_schema("job-request.schema.json", payload)
    if not isinstance(payload, Mapping):  # schema guards this; narrows type for callers
        raise ContractValidationError(
            "CONTRACT_SCHEMA_INVALID", "$", "job payload must be an object"
        )
    try:
        return JobRequest.from_payload(payload)
    except (JobModelError, ValueError, TypeError) as error:
        if isinstance(error, JobModelError):
            raise ContractValidationError(error.code, error.field, str(error)) from None
        raise ContractValidationError(
            "CONTRACT_SEMANTIC_INVALID", "$", "job payload is semantically invalid"
        ) from None


def validate_result_payload(payload: object) -> ModuleResult:
    _validate_with_schema("module-result.schema.json", payload)
    if not isinstance(payload, Mapping):
        raise ContractValidationError(
            "CONTRACT_SCHEMA_INVALID", "$", "result payload must be an object"
        )
    try:
        return ModuleResult.from_payload(payload)
    except (ResultModelError, ValueError, TypeError) as error:
        if isinstance(error, ResultModelError):
            raise ContractValidationError(error.code, error.field, str(error)) from None
        raise ContractValidationError(
            "CONTRACT_SEMANTIC_INVALID", "$", "result payload is semantically invalid"
        ) from None
