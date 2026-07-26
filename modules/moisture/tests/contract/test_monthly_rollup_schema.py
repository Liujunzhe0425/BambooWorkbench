"""Contract tests for private monthly rollup request/response schemas (M-S2)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

MODULE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "monthly"


def _load_schema(name: str) -> dict:
    return json.loads((MODULE_ROOT / "schemas" / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Schema self-validity
# ---------------------------------------------------------------------------


def test_request_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_load_schema("moisture-monthly-rollup-request.schema.json"))


def test_response_schema_is_valid() -> None:
    Draft202012Validator.check_schema(_load_schema("moisture-monthly-rollup-response.schema.json"))


# ---------------------------------------------------------------------------
# Fixture passes schema
# ---------------------------------------------------------------------------


def test_response_fixture_passes_schema() -> None:
    schema = _load_schema("moisture-monthly-rollup-response.schema.json")
    fixture = json.loads((FIXTURES / "rollup-response-example.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(fixture)


# ---------------------------------------------------------------------------
# Request rejects forbidden values
# ---------------------------------------------------------------------------


def test_request_rejects_network_allowed_true() -> None:
    schema = _load_schema("moisture-monthly-rollup-request.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate({
            "schema_version": "1.0", "module_id": "moisture",
            "target_period": {"year": 2026, "month": 3},
            "snapshot_root": "/data", "output_dir": "/out",
            "network_allowed": True,
            "business_config": {"version": "v1", "sha256": "a" * 64},
            "snapshots": [{"month": 3, "path": "/data/03.json", "sha256": "b" * 64}],
        })


def test_request_rejects_empty_snapshots() -> None:
    schema = _load_schema("moisture-monthly-rollup-request.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate({
            "schema_version": "1.0", "module_id": "moisture",
            "target_period": {"year": 2026, "month": 3},
            "snapshot_root": "/data", "output_dir": "/out",
            "network_allowed": False,
            "business_config": {"version": "v1", "sha256": "a" * 64},
            "snapshots": [],
        })


def test_request_rejects_non_moisture_module() -> None:
    schema = _load_schema("moisture-monthly-rollup-request.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate({
            "schema_version": "1.0", "module_id": "boiling",
            "target_period": {"year": 2026, "month": 3},
            "snapshot_root": "/data", "output_dir": "/out",
            "network_allowed": False,
            "business_config": {"version": "v1", "sha256": "a" * 64},
            "snapshots": [{"month": 3, "path": "/data/03.json", "sha256": "b" * 64}],
        })


def test_request_rejects_bad_hash() -> None:
    schema = _load_schema("moisture-monthly-rollup-request.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate({
            "schema_version": "1.0", "module_id": "moisture",
            "target_period": {"year": 2026, "month": 3},
            "snapshot_root": "/data", "output_dir": "/out",
            "network_allowed": False,
            "business_config": {"version": "v1", "sha256": "NOT_A_HASH"},
            "snapshots": [{"month": 3, "path": "/data/03.json", "sha256": "b" * 64}],
        })


# ---------------------------------------------------------------------------
# Response shape constraints
# ---------------------------------------------------------------------------


def test_response_rejects_empty_artifacts() -> None:
    schema = _load_schema("moisture-monthly-rollup-response.schema.json")
    base = json.loads((FIXTURES / "rollup-response-example.json").read_text(encoding="utf-8"))
    base["artifacts"] = []
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(base)


def test_artifact_path_must_not_be_absolute() -> None:
    """Artifact paths are relative; absolute paths containing : or \\ would indicate a leak."""
    fixture_text = (FIXTURES / "rollup-response-example.json").read_text(encoding="utf-8")
    assert "C:\\" not in fixture_text
    assert "/home/" not in fixture_text
    for artifact in json.loads(fixture_text)["artifacts"]:
        assert not artifact["path"].startswith("/")
        assert "\\" not in artifact["path"]


def test_fixture_has_no_secrets() -> None:
    text = (FIXTURES / "rollup-response-example.json").read_text(encoding="utf-8")
    assert "api_key" not in text.lower()
    assert "authorization" not in text.lower()
    assert "password" not in text.lower()
