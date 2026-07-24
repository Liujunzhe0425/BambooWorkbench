"""Contract tests for unified moisture management schemas v1.1 (R2)."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

MODULE_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = MODULE_ROOT / "schemas"
SAMPLES = MODULE_ROOT / "samples" / "management"


def _load(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def req_schema() -> dict:
    return _load("moisture-management-request.schema.json")


@pytest.fixture(scope="module")
def resp_schema() -> dict:
    return _load("moisture-management-response.schema.json")


def _req(op: str, params: dict | None = None) -> dict:
    return {
        "schema_version": "1.1",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": op,
        "data_dir": "C:\\BambooData\\moisture",
        "parameters": params or {},
    }


def _ok(op: str, result: dict | None = None) -> dict:
    return {
        "schema_version": "1.1",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": op,
        "status": "ok",
        "result": result or {},
    }


def _err(op: str, code: str, msg: str) -> dict:
    return {
        "schema_version": "1.1",
        "request_id": "req-001",
        "module_id": "moisture",
        "operation": op,
        "status": "error",
        "error_code": code,
        "message": msg,
    }


# ---------------------------------------------------------------------------
# Schema self-validity
# ---------------------------------------------------------------------------


def test_request_schema_valid(req_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(req_schema)


def test_response_schema_valid(resp_schema: dict) -> None:
    jsonschema.Draft202012Validator.check_schema(resp_schema)


# ---------------------------------------------------------------------------
# 27 operations enumerated
# ---------------------------------------------------------------------------


def test_27_operations_in_schema(req_schema: dict) -> None:
    ops = req_schema["properties"]["operation"]["enum"]
    # 4 legacy + 10 experience + 13 rule = 27
    assert len(ops) == 27
    assert "get_active_rule_identity" in ops
    assert "publish_rule" in ops
    assert "copy_rule_history_to_draft" in ops
    assert "create_experience_draft" in ops


# ---------------------------------------------------------------------------
# No-param operations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op", [
    "list_approved_experiences", "list_history_summaries",
    "list_experience_drafts", "list_experience_approved", "list_experience_history",
    "get_active_rule_identity",
    "list_rule_drafts", "list_current_rules", "list_rule_history",
])
def test_no_param_ops_accept_empty_parameters(req_schema: dict, op: str) -> None:
    jsonschema.validate(_req(op, {}), req_schema, cls=jsonschema.Draft202012Validator)


@pytest.mark.parametrize("op", [
    "list_approved_experiences", "get_active_rule_identity", "list_rule_drafts",
])
def test_no_param_ops_reject_extra_fields(req_schema: dict, op: str) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_req(op, {"extra": 1}), req_schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# Experience operations
# ---------------------------------------------------------------------------


def test_show_experience_requires_id_and_version(req_schema: dict) -> None:
    jsonschema.validate(
        _req("show_experience", {"experience_id": "EXP-X", "version": "1.0.0"}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _req("show_experience", {}), req_schema, cls=jsonschema.Draft202012Validator,
        )


def test_create_experience_requires_document(req_schema: dict) -> None:
    jsonschema.validate(
        _req("create_experience_draft", {"document": "# Test"}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _req("create_experience_draft", {}), req_schema, cls=jsonschema.Draft202012Validator,
        )


def test_publish_experience_requires_hash(req_schema: dict) -> None:
    jsonschema.validate(
        _req("publish_experience", {
            "experience_id": "EXP-X", "version": "1.0.0", "expected_hash": "a" * 64,
        }),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


def test_copy_experience_requires_new_version(req_schema: dict) -> None:
    jsonschema.validate(
        _req("copy_experience_history_to_draft", {
            "experience_id": "EXP-X", "version": "1.0.0",
            "expected_hash": "a" * 64, "new_version": "2.0.0",
        }),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


# ---------------------------------------------------------------------------
# Rule operations
# ---------------------------------------------------------------------------


def test_show_rule_requires_rule_version(req_schema: dict) -> None:
    jsonschema.validate(
        _req("show_rule_package", {"rule_version": "rules-v2"}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


def test_preview_requires_history_ids(req_schema: dict) -> None:
    jsonschema.validate(
        _req("preview_rule_draft", {"rule_version": "rules-v2", "history_ids": ["h1", "h2"]}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _req("preview_rule_draft", {"rule_version": "rules-v2", "history_ids": []}),
            req_schema, cls=jsonschema.Draft202012Validator,
        )


def test_create_rule_requires_manifest_and_yaml(req_schema: dict) -> None:
    jsonschema.validate(
        _req("create_rule_draft", {"manifest": {"id": "pkg-1"}, "rules_yaml": "rules:"}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


def test_retire_rule_requires_sha256(req_schema: dict) -> None:
    jsonschema.validate(
        _req("retire_current_rule", {"expected_rules_sha256": "a" * 64}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


# ---------------------------------------------------------------------------
# History operations
# ---------------------------------------------------------------------------


def test_import_history_requires_input_file(req_schema: dict) -> None:
    jsonschema.validate(
        _req("import_history_summary", {"input_file": "C:\\data\\summary.xlsx"}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


def test_retire_history_requires_history_id(req_schema: dict) -> None:
    jsonschema.validate(
        _req("retire_history_summary", {"history_id": "hist-001"}),
        req_schema, cls=jsonschema.Draft202012Validator,
    )


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------


def test_ok_response_has_result_not_error(resp_schema: dict) -> None:
    jsonschema.validate(
        _ok("get_active_rule_identity", {"active_rule": {"version": "v1", "sha256": "a" * 64}}),
        resp_schema, cls=jsonschema.Draft202012Validator,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**_ok("get_active_rule_identity"), "error_code": "X"},
            resp_schema, cls=jsonschema.Draft202012Validator,
        )


def test_error_response_has_code_and_message_not_result(resp_schema: dict) -> None:
    jsonschema.validate(
        _err("publish_experience", "EXPERIENCE_HASH_CONFLICT", "hash mismatch"),
        resp_schema, cls=jsonschema.Draft202012Validator,
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            {**_err("op", "CODE", "msg"), "result": {}},
            resp_schema, cls=jsonschema.Draft202012Validator,
        )


def test_message_max_300_chars(resp_schema: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _err("op", "CODE", "x" * 301),
            resp_schema, cls=jsonschema.Draft202012Validator,
        )


def test_response_rejects_result_for_different_operation(resp_schema: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _ok(
                "get_active_rule_identity",
                {"rule_items": []},
            ),
            resp_schema,
            cls=jsonschema.Draft202012Validator,
        )


def test_response_rejects_unknown_operation(resp_schema: dict) -> None:
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            _err("unknown_operation", "MANAGEMENT_OPERATION_FAILED", "rejected"),
            resp_schema,
            cls=jsonschema.Draft202012Validator,
        )


def test_management_samples_match_public_v11_schemas(
    req_schema: dict, resp_schema: dict
) -> None:
    sample_paths = sorted(SAMPLES.rglob("*.json"))
    assert sample_paths
    for path in sample_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        schema = req_schema if path.name.endswith(".request.json") else resp_schema
        jsonschema.validate(payload, schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# Reject unknown fields / bad versions
# ---------------------------------------------------------------------------


def test_request_rejects_unknown_top_level(req_schema: dict) -> None:
    instance = {**_req("list_rule_drafts"), "extra": 1}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, req_schema, cls=jsonschema.Draft202012Validator)


def test_response_rejects_unknown_top_level(resp_schema: dict) -> None:
    instance = {**_ok("op"), "extra": 1}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, resp_schema, cls=jsonschema.Draft202012Validator)


def test_rejects_wrong_schema_version(req_schema: dict) -> None:
    instance = _req("list_rule_drafts")
    instance["schema_version"] = "1.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, req_schema, cls=jsonschema.Draft202012Validator)


def test_rejects_non_moisture_module_id(req_schema: dict) -> None:
    instance = _req("list_rule_drafts")
    instance["module_id"] = "boiling"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, req_schema, cls=jsonschema.Draft202012Validator)


# ---------------------------------------------------------------------------
# Schema lock unchanged
# ---------------------------------------------------------------------------


def test_schema_lock_unchanged() -> None:
    lock_path = SCHEMAS / "contracts" / "schema-lock.json"
    if not lock_path.is_file():
        return
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert "moisture-management-request.schema.json" not in str(lock)
    assert "moisture-management-response.schema.json" not in str(lock)
