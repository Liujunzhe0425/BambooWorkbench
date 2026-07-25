import json
from pathlib import Path

import pytest

from core.contracts.manifest import ModuleManifest
from core.modules.management_contract import (
    ModuleManagementContractAdapter,
    ModuleManagementContractError,
)
from core.modules.registry import RegisteredModule


def _module(tmp_path: Path) -> RegisteredModule:
    root = tmp_path / "module"
    schemas = root / "schemas"
    schemas.mkdir(parents=True)
    request_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": [
            "schema_version",
            "request_id",
            "module_id",
            "operation",
            "data_dir",
            "parameters",
        ],
        "properties": {
            "schema_version": {"const": "1.1"},
            "request_id": {"type": "string"},
            "module_id": {"const": "moisture"},
            "operation": {"const": "get_active_rule_identity"},
            "data_dir": {"type": "string"},
            "parameters": {"type": "object", "maxProperties": 0},
        },
        "additionalProperties": False,
    }
    response_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "required": ["schema_version", "request_id", "module_id", "operation", "status", "result"],
        "properties": {
            "schema_version": {"const": "1.1"},
            "request_id": {"type": "string"},
            "module_id": {"const": "moisture"},
            "operation": {"const": "get_active_rule_identity"},
            "status": {"const": "ok"},
            "result": {"type": "object"},
        },
        "additionalProperties": False,
    }
    (schemas / "request.json").write_text(json.dumps(request_schema), encoding="utf-8")
    (schemas / "response.json").write_text(json.dumps(response_schema), encoding="utf-8")
    manifest = ModuleManifest.model_validate(
        {
            "schema_version": "1.0",
            "module_id": "moisture",
            "module_name": "水分",
            "module_version": "1.1.1",
            "entrypoint": "run.bat",
            "management_entrypoint": "manage.bat",
            "management_contract": {
                "schema_version": "1.1",
                "request_schema": "schemas/request.json",
                "response_schema": "schemas/response.json",
            },
            "supported_extensions": [".xlsx"],
            "supports_single_file": True,
            "supports_batch": True,
            "supports_incremental": True,
            "requires_network": False,
        }
    )
    return RegisteredModule(manifest, root, False, "healthy")


def test_adapter_validates_request_response_and_identity(tmp_path: Path) -> None:
    adapter = ModuleManagementContractAdapter(_module(tmp_path))
    request = adapter.request(
        request_id="request-1",
        operation="get_active_rule_identity",
        data_dir=tmp_path.resolve(),
    )
    response = adapter.validate_response(
        {
            "schema_version": "1.1",
            "request_id": "request-1",
            "module_id": "moisture",
            "operation": "get_active_rule_identity",
            "status": "ok",
            "result": {"active_rule": {"version": "v1", "sha256": "a" * 64}},
        },
        request=request,
    )
    assert response["status"] == "ok"

    with pytest.raises(ModuleManagementContractError):
        adapter.validate_response({**response, "request_id": "other"}, request=request)
