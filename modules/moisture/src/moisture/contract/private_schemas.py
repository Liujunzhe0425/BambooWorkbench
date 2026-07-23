"""Load and validate versioned moisture-private payload schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from moisture.runtime_paths import module_root as runtime_module_root

PRIVATE_SCHEMA_NAMES = (
    "module-config.schema.json",
    "history-index.schema.json",
    "approved-experience-catalog.schema.json",
    "ai-analysis-request.schema.json",
    "ai-analysis-response.schema.json",
    "ai-analysis-result.schema.json",
)


class PrivateSchemaError(ValueError):
    """A stable failure to load or validate a module-private payload."""


def load_private_schema(name: str, module_root: Path | None = None) -> dict[str, Any]:
    if name not in PRIVATE_SCHEMA_NAMES:
        raise PrivateSchemaError("unknown private schema")
    root = module_root or runtime_module_root()
    try:
        payload = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, SchemaError) as error:
        raise PrivateSchemaError("private schema is unavailable or invalid") from error
    if not isinstance(payload, dict):
        raise PrivateSchemaError("private schema must be an object")
    return payload


def validate_private_payload(
    name: str,
    payload: object,
    module_root: Path | None = None,
) -> None:
    schema = load_private_schema(name, module_root)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(payload)), None)
    if error is not None:
        raise PrivateSchemaError("payload violates private schema") from None
