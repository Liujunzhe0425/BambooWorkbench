"""Strict versioned configuration for module-owned operations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_HASH = re.compile(r"^[0-9a-f]{64}$")


class ModuleConfigError(ValueError):
    """The optional module-owned configuration is invalid."""


class ModuleOperation(StrEnum):
    SUMMARY = "summary"
    APPEND_SUMMARY = "append_summary"
    AI_REPORT = "ai_report"


@dataclass(frozen=True, slots=True)
class ExperienceSelection:
    entry_id: str
    version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class RuleSelection:
    version: str
    sha256: str


@dataclass(frozen=True, slots=True)
class ModuleConfig:
    schema_version: str
    operation: ModuleOperation
    default_year: int | None = None
    base_summary_input_index: int | None = None
    new_raw_input_indexes: tuple[int, ...] = ()
    current_summary_input_index: int | None = None
    history_ids: tuple[str, ...] = ()
    experience_selections: tuple[ExperienceSelection, ...] = ()
    question: str | None = None
    rule_selection: RuleSelection | None = None


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModuleConfigError("duplicate configuration key")
        result[key] = value
    return result


def _read_payload(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ModuleConfigError("configuration must be readable UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise ModuleConfigError("configuration must be a JSON object")
    return payload


def _default_year(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 1900 <= value <= 2100:
        raise ModuleConfigError("default_year must be an integer from 1900 to 2100")
    return value


def _stable_ids(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 100:
        raise ModuleConfigError(f"{field} must be an array with at most 100 items")
    if any(not isinstance(item, str) or not _STABLE_ID.fullmatch(item) for item in value):
        raise ModuleConfigError(f"{field} contains an invalid stable ID")
    if len(set(value)) != len(value):
        raise ModuleConfigError(f"{field} contains duplicate IDs")
    return tuple(value)


def _experience_selections(value: object) -> tuple[ExperienceSelection, ...]:
    if not isinstance(value, list) or len(value) > 50:
        raise ModuleConfigError("experience_selections must be an array with at most 50 items")
    selections: list[ExperienceSelection] = []
    identities: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"entry_id", "version", "sha256"}:
            raise ModuleConfigError("experience selection has an invalid structure")
        entry_id = item["entry_id"]
        version = item["version"]
        sha256 = item["sha256"]
        if (
            not isinstance(entry_id, str)
            or not _STABLE_ID.fullmatch(entry_id)
            or not isinstance(version, str)
            or not _STABLE_ID.fullmatch(version)
            or not isinstance(sha256, str)
            or not _HASH.fullmatch(sha256)
        ):
            raise ModuleConfigError("experience selection contains an invalid value")
        identity = (entry_id, version)
        if identity in identities:
            raise ModuleConfigError("experience selection contains a duplicate version")
        identities.add(identity)
        selections.append(ExperienceSelection(entry_id, version, sha256))
    return tuple(selections)


def _rule_selection(value: object) -> RuleSelection | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"version", "sha256"}:
        raise ModuleConfigError("rule_selection has an invalid structure")
    version = value["version"]
    sha256 = value["sha256"]
    if (
        not isinstance(version, str)
        or not _STABLE_ID.fullmatch(version)
        or not isinstance(sha256, str)
        or not _HASH.fullmatch(sha256)
    ):
        raise ModuleConfigError("rule_selection contains an invalid value")
    return RuleSelection(version, sha256)


def _append_input_indexes(
    value: object,
    *,
    input_count: int,
) -> tuple[int, tuple[int, ...]]:
    if not isinstance(value, list) or not 2 <= len(value) <= 100:
        raise ModuleConfigError("append_summary inputs must contain 2 to 100 roles")
    base_indexes: list[int] = []
    raw_indexes: list[int] = []
    seen_indexes: set[int] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"role", "input_index"}:
            raise ModuleConfigError("append_summary input role has an invalid structure")
        role = item["role"]
        input_index = item["input_index"]
        if role not in {"base_summary", "new_raw"}:
            raise ModuleConfigError("append_summary input role is not supported")
        if type(input_index) is not int or not 0 <= input_index < input_count:
            raise ModuleConfigError("append_summary input_index is out of range")
        if input_index in seen_indexes:
            raise ModuleConfigError("append_summary input_index is duplicated")
        seen_indexes.add(input_index)
        if role == "base_summary":
            base_indexes.append(input_index)
        else:
            raw_indexes.append(input_index)
    if len(base_indexes) != 1 or not raw_indexes:
        raise ModuleConfigError(
            "append_summary requires exactly one base_summary and at least one new_raw"
        )
    if seen_indexes != set(range(input_count)):
        raise ModuleConfigError("append_summary must assign every job input exactly once")
    return base_indexes[0], tuple(raw_indexes)


def load_module_config(path: Path | None, *, input_count: int) -> ModuleConfig:
    """Load legacy summary config or the strict v1.0 operation config."""

    payload = _read_payload(path)
    if not payload or set(payload) <= {"default_year"}:
        return ModuleConfig(
            schema_version="1.0",
            operation=ModuleOperation.SUMMARY,
            default_year=_default_year(payload.get("default_year")),
        )

    operation = payload.get("operation")
    if payload.get("schema_version") != "1.0":
        raise ModuleConfigError("schema_version must be 1.0")
    try:
        parsed_operation = ModuleOperation(operation)
    except (TypeError, ValueError):
        raise ModuleConfigError("operation must be summary, append_summary, or ai_report") from None

    if parsed_operation is ModuleOperation.SUMMARY:
        if set(payload) - {
            "schema_version",
            "operation",
            "default_year",
            "rule_selection",
        }:
            raise ModuleConfigError("summary configuration contains unknown fields")
        return ModuleConfig(
            schema_version="1.0",
            operation=parsed_operation,
            default_year=_default_year(payload.get("default_year")),
            rule_selection=_rule_selection(payload.get("rule_selection")),
        )

    if parsed_operation is ModuleOperation.APPEND_SUMMARY:
        allowed = {
            "schema_version",
            "operation",
            "inputs",
            "default_year",
            "rule_selection",
        }
        if set(payload) - allowed:
            raise ModuleConfigError("append_summary configuration contains unknown fields")
        if not {"schema_version", "operation", "inputs"} <= set(payload):
            raise ModuleConfigError("append_summary configuration is incomplete")
        base_index, raw_indexes = _append_input_indexes(
            payload["inputs"],
            input_count=input_count,
        )
        return ModuleConfig(
            schema_version="1.0",
            operation=parsed_operation,
            default_year=_default_year(payload.get("default_year")),
            base_summary_input_index=base_index,
            new_raw_input_indexes=raw_indexes,
            rule_selection=_rule_selection(payload.get("rule_selection")),
        )

    allowed = {
        "schema_version",
        "operation",
        "inputs",
        "history_ids",
        "experience_selections",
        "question",
        "rule_selection",
    }
    if set(payload) - allowed:
        raise ModuleConfigError("ai_report configuration contains unknown fields")
    if not (allowed - {"rule_selection"}) <= set(payload):
        raise ModuleConfigError("ai_report configuration is incomplete")

    inputs = payload["inputs"]
    if (
        not isinstance(inputs, list)
        or len(inputs) != 1
        or not isinstance(inputs[0], dict)
        or set(inputs[0]) != {"role", "input_index"}
        or inputs[0].get("role") != "current_summary"
    ):
        raise ModuleConfigError("ai_report requires exactly one current_summary input role")
    input_index = inputs[0].get("input_index")
    if type(input_index) is not int or not 0 <= input_index < input_count:
        raise ModuleConfigError("current_summary input_index is out of range")

    question = payload["question"]
    if not isinstance(question, str) or not 1 <= len(question.strip()) <= 2000:
        raise ModuleConfigError("question must contain 1 to 2000 characters")
    if any(ord(character) < 32 and character not in "\t\n\r" for character in question):
        raise ModuleConfigError("question contains control characters")

    return ModuleConfig(
        schema_version="1.0",
        operation=parsed_operation,
        current_summary_input_index=input_index,
        history_ids=_stable_ids(payload["history_ids"], "history_ids"),
        experience_selections=_experience_selections(payload["experience_selections"]),
        question=question.strip(),
        rule_selection=_rule_selection(payload.get("rule_selection")),
    )
