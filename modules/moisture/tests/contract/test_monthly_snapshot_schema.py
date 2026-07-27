from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft202012Validator

MODULE_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = MODULE_ROOT / "tests" / "fixtures" / "monthly"


def test_private_monthly_snapshot_schema_is_valid_and_not_a_central_contract() -> None:
    schema_path = MODULE_ROOT / "schemas" / "moisture-monthly-snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == "urn:bamboo:moisture:monthly-snapshot:1.0"
    assert schema["$defs"]["record"]["properties"]["record_id"] == {
        "$ref": "#/$defs/business_record_id"
    }
    assert not (MODULE_ROOT / "schemas" / "contracts" / schema_path.name).exists()


def test_manifest_claims_approved_framework_monthly_rollup_contract() -> None:
    manifest = json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))

    assert "monthly_rollup" in manifest["capabilities"]
    assert manifest["monthly_rollup"] == {
        "schema_version": "1.0",
        "entrypoint": "run_module.bat",
        "snapshot_schema": "schemas/moisture-monthly-snapshot.schema.json",
        "request_schema": "schemas/moisture-monthly-rollup-public-request.schema.json",
        "response_schema": "schemas/moisture-monthly-rollup-public-response.schema.json",
        "learning_schema": "schemas/moisture-learning-public.schema.json",
    }


def test_fixture_snapshot_passes_schema() -> None:
    schema_path = MODULE_ROOT / "schemas" / "moisture-monthly-snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fixture = json.loads((FIXTURES / "snapshot-example.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(fixture)


def test_schema_accepts_unicode_record_id_and_rejects_unsafe_ids() -> None:
    schema_path = MODULE_ROOT / "schemas" / "moisture-monthly-snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fixture = json.loads((FIXTURES / "snapshot-example.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    fixture["records"][0]["record_id"] = "001-4.10 供应商甲原竹丝水分检测（2）"
    fixture["records"][0]["traceability"]["source_display_name"] = (
        "001-4.10 供应商甲原竹丝水分检测（2）.xlsx"
    )
    validator.validate(fixture)

    for unsafe in ("../批次", r"C:\客户\批次", "客户/批次", "客户\x00批次"):
        fixture["records"][0]["record_id"] = unsafe
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(fixture)


def test_fixture_has_no_absolute_paths_or_secrets() -> None:
    text = (FIXTURES / "snapshot-example.json").read_text(encoding="utf-8")
    assert "C:\\" not in text
    assert "D:\\" not in text
    assert "api_key" not in text.lower()
    assert "authorization" not in text.lower()


@pytest.mark.parametrize("field", [
    "schema_version", "module_id", "period", "rule_snapshot", "records",
])
def test_snapshot_top_level_required_fields(field: str) -> None:
    schema_path = MODULE_ROOT / "schemas" / "moisture-monthly-snapshot.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    fixture = json.loads((FIXTURES / "snapshot-example.json").read_text(encoding="utf-8"))
    broken = {k: v for k, v in fixture.items() if k != field}
    with pytest.raises(jsonschema.ValidationError):
        Draft202012Validator(schema).validate(broken)
