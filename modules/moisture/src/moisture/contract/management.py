"""Strict module-local adapter for the framework management contract."""

from __future__ import annotations

import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from moisture.runtime_paths import module_root

REQUEST_SCHEMA = "module-management-request.schema.json"
RESPONSE_SCHEMA = "module-management-response.schema.json"
OPERATIONS = {
    "list_approved_experiences",
    "import_history_summary",
    "list_history_summaries",
    "retire_history_summary",
}


class ManagementContractError(ValueError):
    """A management request or response violates the framework contract."""


def _schema(name: str) -> dict[str, Any]:
    path = module_root() / "schemas" / "contracts" / name
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManagementContractError("管理合同不可用") from error
    return payload


def _validate(name: str, payload: object) -> dict[str, Any]:
    try:
        Draft202012Validator(_schema(name)).validate(payload)
    except JsonSchemaValidationError as error:
        raise ManagementContractError("管理数据不符合合同") from error
    if not isinstance(payload, dict):
        raise ManagementContractError("管理数据必须是对象")
    return payload


def validate_management_request(payload: object) -> dict[str, Any]:
    """Validate the public schema and operation-specific request fields."""

    request = _validate(REQUEST_SCHEMA, payload)
    if request["module_id"] != "moisture" or request["operation"] not in OPERATIONS:
        raise ManagementContractError("管理请求不属于水分模块")
    operation = request["operation"]
    input_file = request.get("input_file")
    history_id = request.get("history_id")
    if operation == "import_history_summary":
        valid = input_file is not None and history_id is None
    elif operation == "retire_history_summary":
        valid = history_id is not None and input_file is None
    else:
        valid = input_file is None and history_id is None
    if not valid:
        raise ManagementContractError("管理请求字段与操作不匹配")
    return request


def validate_management_response(payload: object) -> dict[str, Any]:
    """Validate a response before it is atomically published."""

    return _validate(RESPONSE_SCHEMA, payload)
