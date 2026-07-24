"""Strict adapters for legacy and unified moisture management contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from moisture.runtime_paths import module_root

LEGACY_REQUEST_SCHEMA = "module-management-request.schema.json"
LEGACY_RESPONSE_SCHEMA = "module-management-response.schema.json"
UNIFIED_REQUEST_SCHEMA = "moisture-management-request.schema.json"
UNIFIED_RESPONSE_SCHEMA = "moisture-management-response.schema.json"

LEGACY_OPERATIONS = frozenset(
    {
        "list_approved_experiences",
        "import_history_summary",
        "list_history_summaries",
        "retire_history_summary",
    }
)
EXPERIENCE_OPERATIONS = frozenset(
    {
        "list_experience_drafts",
        "list_experience_approved",
        "list_experience_history",
        "show_experience",
        "validate_experience_draft",
        "create_experience_draft",
        "update_experience_draft",
        "publish_experience",
        "retire_experience",
        "copy_experience_history_to_draft",
    }
)
RULE_OPERATIONS = frozenset(
    {
        "get_active_rule_identity",
        "list_rule_drafts",
        "list_current_rules",
        "list_rule_history",
        "show_rule_package",
        "validate_rule_draft",
        "preview_rule_draft",
        "create_rule_draft",
        "update_rule_draft",
        "publish_rule",
        "retire_current_rule",
        "restore_rule_version",
        "copy_rule_history_to_draft",
    }
)
OPERATIONS = LEGACY_OPERATIONS | EXPERIENCE_OPERATIONS | RULE_OPERATIONS


class ManagementContractError(ValueError):
    """A management request or response violates its public JSON Schema."""


def _schema_path(name: str, *, legacy: bool) -> Path:
    base = module_root() / "schemas"
    return (base / "contracts" / name) if legacy else (base / name)


def _schema(name: str, *, legacy: bool) -> dict[str, Any]:
    path = _schema_path(name, legacy=legacy)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ManagementContractError("管理合同不可用") from error
    return payload


def _validate(name: str, payload: object, *, legacy: bool) -> dict[str, Any]:
    try:
        Draft202012Validator(_schema(name, legacy=legacy)).validate(payload)
    except JsonSchemaValidationError as error:
        raise ManagementContractError("管理数据不符合合同") from error
    if not isinstance(payload, dict):
        raise ManagementContractError("管理数据必须是对象")
    return payload


def _validate_legacy_request(payload: object) -> dict[str, Any]:
    request = _validate(LEGACY_REQUEST_SCHEMA, payload, legacy=True)
    if request["module_id"] != "moisture" or request["operation"] not in LEGACY_OPERATIONS:
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


def validate_management_request(payload: object) -> dict[str, Any]:
    """Validate one v1.0 compatibility or unified v1.1 request."""

    if not isinstance(payload, dict):
        raise ManagementContractError("管理数据必须是对象")
    version = payload.get("schema_version")
    if version == "1.0":
        return _validate_legacy_request(payload)
    if version != "1.1":
        raise ManagementContractError("管理合同版本不受支持")
    request = _validate(UNIFIED_REQUEST_SCHEMA, payload, legacy=False)
    if request["module_id"] != "moisture" or request["operation"] not in OPERATIONS:
        raise ManagementContractError("管理请求不属于水分模块")
    parameters = request["parameters"]
    document = parameters.get("document")
    if isinstance(document, str) and len(document.encode("utf-8")) > 65_536:
        raise ManagementContractError("经验文档超过合同预算")
    rules_yaml = parameters.get("rules_yaml")
    if isinstance(rules_yaml, str) and len(rules_yaml.encode("utf-8")) > 262_144:
        raise ManagementContractError("规则文档超过合同预算")
    return request


def validate_management_response(payload: object) -> dict[str, Any]:
    """Validate a response before it is atomically published."""

    if not isinstance(payload, dict):
        raise ManagementContractError("管理数据必须是对象")
    version = payload.get("schema_version")
    if version == "1.0":
        return _validate(LEGACY_RESPONSE_SCHEMA, payload, legacy=True)
    if version == "1.1":
        return _validate(UNIFIED_RESPONSE_SCHEMA, payload, legacy=False)
    raise ManagementContractError("管理合同版本不受支持")
