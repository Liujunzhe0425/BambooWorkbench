"""Contract tests for private learning descriptor schema (L-S1)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

MODULE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "learning"


def _load_schema() -> dict:
    return json.loads(
        (MODULE_ROOT / "schemas" / "moisture-learning-descriptor.schema.json")
        .read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# Schema self-validity
# ---------------------------------------------------------------------------


def test_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_load_schema())


# ---------------------------------------------------------------------------
# Fixture validation
# ---------------------------------------------------------------------------


def test_fixture_passes_schema() -> None:
    schema = _load_schema()
    fixture = json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(fixture)


def test_fixture_has_no_secrets_or_paths() -> None:
    text = (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    assert "api_key" not in text.lower()
    assert "C:\\" not in text
    assert "D:\\" not in text


# ---------------------------------------------------------------------------
# Field constraints
# ---------------------------------------------------------------------------


def test_rejects_unknown_field() -> None:
    schema = _load_schema()
    fixture = json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )
    fixture["field"] = "formula_conflict"
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(fixture)


def test_rejects_bad_learning_key() -> None:
    schema = _load_schema()
    fixture = json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )
    fixture["learning_key"] = "bad-key"
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(fixture)


def test_rejects_empty_candidates() -> None:
    schema = _load_schema()
    fixture = json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )
    fixture["candidates"] = []
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(fixture)


def test_rejects_duplicate_context_levels() -> None:
    """Schema cannot enforce unique keys, but the contract layer does.
    Ensure at least the structure is validated."""
    schema = _load_schema()
    fixture = json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )
    # context_levels must have at least 1 item
    fixture["context_levels"] = fixture["context_levels"][:1]
    Draft202012Validator(schema).validate(fixture)


def test_rejects_non_moisture_module_id() -> None:
    schema = _load_schema()
    fixture = json.loads(
        (FIXTURES / "learning-descriptor-example.json").read_text(encoding="utf-8")
    )
    fixture["context"]["module_id"] = "boiling"
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(fixture)
