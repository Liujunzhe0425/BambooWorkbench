"""Read and validate an immutable, module-bundled rule package."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from moisture.domain.enums import DisplayColor
from moisture.domain.rules import RuleDefinition, RulePackageSnapshot
from moisture.runtime_paths import module_root as runtime_module_root


class RulePackageValidationError(ValueError):
    """The package structure or rule values are invalid."""


class RulePackageIntegrityError(RulePackageValidationError):
    """The exact rules file bytes do not match the published digest."""


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False):
    pairs = loader.construct_pairs(node, deep=deep)
    result: dict[Any, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RulePackageValidationError(f"duplicate YAML key: {key}")
        result[key] = value
    return result


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RulePackageValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


_RULE_KEYS = {
    "rule_id",
    "rule_type",
    "message",
    "field",
    "operator",
    "threshold",
    "lower",
    "upper",
    "mode",
    "fields",
    "tolerance",
    "rule_ids",
    "combinator",
    "color",
    "applicable_materials",
    "applicable_seasons",
    "applicable_suppliers",
    "customer_confirmation_status",
}


def _decimal(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise RulePackageValidationError(f"{field} must be decimal-compatible")
    try:
        converted = Decimal(str(value))
    except InvalidOperation as error:
        raise RulePackageValidationError(f"{field} must be a decimal") from error
    if not converted.is_finite():
        raise RulePackageValidationError(f"{field} must be finite")
    return converted


def _string_tuple(payload: dict[str, Any], field: str) -> tuple[str, ...]:
    value = payload.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RulePackageValidationError(f"{field} must be an array of strings")
    return tuple(value)


def _definition(payload: object) -> RuleDefinition:
    if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
        raise RulePackageValidationError("each rule definition must be an object")
    unknown = set(payload) - _RULE_KEYS
    if unknown:
        raise RulePackageValidationError(f"unknown rule property: {sorted(unknown)[0]}")
    rule_id = payload.get("rule_id")
    rule_type = payload.get("rule_type")
    if not isinstance(rule_id, str) or not isinstance(rule_type, str):
        raise RulePackageValidationError("rule_id and rule_type must be strings")
    if payload.get("message") is not None and not isinstance(payload["message"], str):
        raise RulePackageValidationError("message must be a string or null")
    try:
        return RuleDefinition(
            rule_id=rule_id,
            rule_type=rule_type,
            message=payload.get("message") if isinstance(payload.get("message"), str) else None,
            field=payload.get("field") if isinstance(payload.get("field"), str) else None,
            operator=payload.get("operator") if isinstance(payload.get("operator"), str) else None,
            threshold=_decimal(payload.get("threshold"), "threshold"),
            lower=_decimal(payload.get("lower"), "lower"),
            upper=_decimal(payload.get("upper"), "upper"),
            mode=payload.get("mode"),
            fields=_string_tuple(payload, "fields"),
            tolerance=_decimal(payload.get("tolerance"), "tolerance"),
            rule_ids=_string_tuple(payload, "rule_ids"),
            combinator=payload.get("combinator"),
            color=DisplayColor(payload.get("color", "none")),
            applicable_materials=_string_tuple(payload, "applicable_materials"),
            applicable_seasons=_string_tuple(payload, "applicable_seasons"),
            applicable_suppliers=_string_tuple(payload, "applicable_suppliers"),
            customer_confirmation_status=payload.get("customer_confirmation_status"),
        )
    except (TypeError, ValueError) as error:
        raise RulePackageValidationError(f"invalid rule {rule_id}: {error}") from error


class RulePackageLoader:
    def __init__(self, schema_path: Path | None = None) -> None:
        default_schema = runtime_module_root() / "schemas" / "rule-package.schema.json"
        self.schema_path = schema_path or default_schema

    def load(self, package_dir: Path) -> RulePackageSnapshot:
        root = package_dir.resolve(strict=True)
        manifest_path = root / "rule-package.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise RulePackageValidationError("rule-package.json must be a regular file")
        try:
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_json,
            )
            schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
            Draft202012Validator(schema).validate(manifest)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise RulePackageValidationError(f"invalid rule package manifest: {error}") from error
        except Exception as error:
            if isinstance(error, RulePackageValidationError):
                raise
            raise RulePackageValidationError(
                f"rule package schema validation failed: {error}"
            ) from error

        rules_path = root / manifest["rules_file"]
        if rules_path.parent != root or rules_path.name != "rules.yaml":
            raise RulePackageValidationError("rules_file must be the local rules.yaml")
        if rules_path.is_symlink() or not rules_path.is_file():
            raise RulePackageValidationError("rules.yaml must be a regular file")
        try:
            rules_bytes = rules_path.read_bytes()
        except OSError as error:
            raise RulePackageValidationError(f"cannot read rules.yaml: {error}") from error
        actual_hash = hashlib.sha256(rules_bytes).hexdigest()
        if actual_hash != manifest["rules_sha256"]:
            raise RulePackageIntegrityError("rules.yaml SHA-256 does not match manifest")
        try:
            payload = yaml.load(rules_bytes.decode("utf-8"), Loader=_UniqueKeyLoader)
        except (UnicodeError, yaml.YAMLError) as error:
            raise RulePackageValidationError(f"invalid rules YAML: {error}") from error
        if not isinstance(payload, dict) or set(payload) != {"definitions"}:
            raise RulePackageValidationError("rules.yaml must contain only definitions")
        definitions_payload = payload["definitions"]
        if not isinstance(definitions_payload, list) or not definitions_payload:
            raise RulePackageValidationError("definitions must be a non-empty array")
        definitions = tuple(_definition(item) for item in definitions_payload)
        if any(
            definition.customer_confirmation_status != manifest["customer_confirmation_status"]
            for definition in definitions
        ):
            raise RulePackageValidationError(
                "rule confirmation status must match package confirmation status"
            )
        try:
            return RulePackageSnapshot(definitions=definitions, **manifest)
        except (TypeError, ValueError) as error:
            raise RulePackageValidationError(f"invalid rule package: {error}") from error
