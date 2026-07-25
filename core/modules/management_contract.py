from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError

from core.platform.path_safety import resolve_contained_file

from .registry import RegisteredModule


class ModuleManagementContractError(ValueError):
    """A module-owned management envelope failed framework validation."""


class ModuleManagementContractAdapter:
    def __init__(self, module: RegisteredModule) -> None:
        descriptor = module.manifest.management_contract
        if descriptor is None:
            raise ModuleManagementContractError("module has no versioned management contract")
        self.module = module
        self.schema_version = descriptor.schema_version
        self.request_validator = self._validator(descriptor.request_schema, "request schema")
        self.response_validator = self._validator(descriptor.response_schema, "response schema")

    def request(
        self,
        *,
        request_id: str,
        operation: str,
        data_dir: Path,
        parameters: dict[str, object] | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "request_id": request_id,
            "module_id": self.module.manifest.module_id.value,
            "operation": operation,
            "data_dir": str(data_dir),
            "parameters": dict(parameters or {}),
        }
        self.validate_request(payload)
        return payload

    def validate_request(self, payload: object) -> dict[str, object]:
        return self._validate(self.request_validator, payload, "management request")

    def validate_response(
        self,
        payload: object,
        *,
        request: dict[str, object],
    ) -> dict[str, object]:
        response = self._validate(self.response_validator, payload, "management response")
        for field in ("request_id", "module_id", "operation"):
            if response.get(field) != request.get(field):
                raise ModuleManagementContractError(
                    f"management response {field} does not match request"
                )
        return response

    def _validator(self, raw_path: str, label: str) -> Draft202012Validator:
        try:
            path = resolve_contained_file(
                self.module.path / raw_path,
                self.module.path,
                label,
                reject_link=True,
            )
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
        except Exception as error:
            raise ModuleManagementContractError(f"module {label} is unavailable") from error
        return Draft202012Validator(schema)

    @staticmethod
    def _validate(
        validator: Draft202012Validator,
        payload: object,
        label: str,
    ) -> dict[str, object]:
        try:
            validator.validate(payload)
        except JsonSchemaValidationError as error:
            raise ModuleManagementContractError(f"{label} violates module schema") from error
        if not isinstance(payload, dict):
            raise ModuleManagementContractError(f"{label} must be an object")
        return dict(payload)
