"""Contract tests for experience management request/response schemas (A-E-S1)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import jsonschema
import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = MODULE_ROOT / "schemas"
SAMPLES = MODULE_ROOT / "samples" / "management" / "experience"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _load_schema(name: str) -> dict:
    path = SCHEMAS / name
    assert path.is_file(), f"Schema missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def request_schema() -> dict:
    return _load_schema("experience-management-request.schema.json")


@pytest.fixture(scope="module")
def response_schema() -> dict:
    return _load_schema("experience-management-response.schema.json")


def _valid_list_request(op: str) -> dict:
    return {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": op,
        "data_dir": "C:\\BambooData\\moisture",
    }


def _valid_request(op: str, **extra: object) -> dict:
    base: dict[str, object] = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": op,
        "data_dir": "C:\\BambooData\\moisture",
    }
    base.update(extra)
    return base


_VALID_DOC = (
    "---\nexperience_id: EXP-DEMO-001\nversion: 1.0.0\n"
    "title: Test\nsource: internal/lab\nstatus: draft\n"
    "effective_at: 2026-01-01T00:00:00+00:00\n"
    "applicable_suppliers:\n  - 甲\napplicable_materials:\n  - 竹丝\n"
    "applicable_seasons:\n  - all\napplicable_metrics:\n  - mean\n"
    "author: tester\nreviewer: reviewer\nevidence_sources:\n  - internal/ev\n"
    "supersedes:\n---\n\n# Test\n"
)


# ---------------------------------------------------------------------------
# Schema self-validity
# ---------------------------------------------------------------------------


def test_request_schema_is_valid_draft_2020_12(request_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(request_schema)


def test_response_schema_is_valid_draft_2020_12(response_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(response_schema)


# ---------------------------------------------------------------------------
# Public examples have migrated to the unified v1.1 contract
# ---------------------------------------------------------------------------


def test_public_experience_samples_use_unified_v11_envelopes() -> None:
    sample_paths = sorted(SAMPLES.glob("*.json"))
    assert sample_paths
    for sample_path in sample_paths:
        instance = json.loads(sample_path.read_text(encoding="utf-8"))
        assert instance["schema_version"] == "1.1"
        if sample_path.name.endswith(".request.json"):
            assert "parameters" in instance
        elif instance["status"] == "ok":
            assert "result" in instance


# ---------------------------------------------------------------------------
# Unknown fields
# ---------------------------------------------------------------------------


def test_request_rejects_unknown_fields(request_schema: dict) -> None:
    instance = {**_valid_list_request("list_experience_drafts"), "unknown_field": 1}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


def test_response_rejects_unknown_fields(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": "list_experience_drafts",
        "status": "ok",
        "experience_items": [],
        "unknown_field": 1,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# operation / field mismatches
# ---------------------------------------------------------------------------


def test_list_rejects_document(request_schema: dict) -> None:
    instance = {**_valid_list_request("list_experience_drafts"), "document": "x"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


def test_list_rejects_experience_id(request_schema: dict) -> None:
    instance = {**_valid_list_request("list_experience_approved"), "experience_id": "EXP-X"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


def test_show_requires_id_and_version(request_schema: dict) -> None:
    instance = _valid_request("show_experience")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)

    ok = _valid_request("show_experience", experience_id="EXP-X", version="1.0.0")
    jsonschema.validate(ok, request_schema, cls=jsonschema.Draft202012Validator)


def test_publish_rejects_document(request_schema: dict) -> None:
    instance = _valid_request(
        "publish_experience",
        experience_id="EXP-X", version="1.0.0",
        expected_hash="a" * 64, document="x",
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


def test_copy_requires_new_version(request_schema: dict) -> None:
    instance = _valid_request(
        "copy_experience_history_to_draft",
        experience_id="EXP-X", version="1.0.0", expected_hash="a" * 64,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# ID / SemVer / hash format
# ---------------------------------------------------------------------------


def test_rejects_non_semver_version(request_schema: dict) -> None:
    instance = _valid_request("show_experience", experience_id="EXP-X", version="v1")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


def test_rejects_non_lowercase_hash(request_schema: dict) -> None:
    instance = _valid_request(
        "publish_experience",
        experience_id="EXP-X", version="1.0.0",
        expected_hash="A" * 64,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, request_schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_list_response_rejects_document(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": "list_experience_drafts",
        "status": "ok",
        "experience_items": [
            {
                "experience_id": "EXP-X", "version": "1.0.0", "status": "draft",
                "title": "T", "source": "src", "sha256": "a" * 64,
                "effective_at": "2026-01-01T00:00:00+00:00",
                "applicable_suppliers": ["*"],
                "applicable_materials": ["原竹丝"],
                "applicable_seasons": ["*"],
                "applicable_metrics": ["mean"],
                "supersedes": None,
                "document": "should-not-be-here",
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


def test_single_response_rejects_path(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": "show_experience",
        "status": "ok",
        "experience": {
            "experience_id": "EXP-X", "version": "1.0.0", "status": "draft",
            "sha256": "a" * 64, "document": "# Test",
            "path": "draft/EXP-X-1.0.0.md",
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


def test_unknown_error_code_rejected(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": "update_experience_draft",
        "status": "error",
        "error_code": "MADE_UP_CODE",
        "message": "something",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


def test_item_list_must_not_have_experience(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": "list_experience_drafts",
        "status": "ok",
        "experience_items": [],
        "experience": {
            "experience_id": "EXP-X", "version": "1.0.0", "status": "draft",
            "sha256": "a" * 64, "document": "# Test",
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


def test_response_requires_identity_fields(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "status": "ok",
        "experience_items": [],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


def test_response_rejects_semver_prefix_match(response_schema: dict) -> None:
    instance = {
        "schema_version": "1.0",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": "show_experience",
        "status": "ok",
        "experience": {
            "experience_id": "EXP-X",
            "version": "1.0.0-invalid space",
            "status": "draft",
            "sha256": "a" * 64,
            "document": "# Test",
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, response_schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# Schema lock unchanged
# ---------------------------------------------------------------------------


def test_schema_lock_unchanged() -> None:
    lock_path = SCHEMAS / "contracts" / "schema-lock.json"
    if not lock_path.is_file():
        return
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert "experience-management-request.schema.json" not in str(lock)
    assert "experience-management-response.schema.json" not in str(lock)
