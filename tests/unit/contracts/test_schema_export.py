import json
from pathlib import Path

from app.tools.export_schemas import export_contracts
from core.contracts.job import JobRequest
from core.contracts.manifest import ModuleManifest
from core.contracts.result import ModuleResult

EXPECTED_FILES = [
    "contracts/schemas/module-manifest.schema.json",
    "contracts/schemas/job-request.schema.json",
    "contracts/schemas/module-result.schema.json",
    "contracts/schemas/module-management-request.schema.json",
    "contracts/schemas/module-management-response.schema.json",
    "contracts/examples/module.json",
    "contracts/examples/job.json",
    "contracts/examples/result.json",
]


def test_export_contracts_writes_expected_valid_json(tmp_path: Path) -> None:
    written = export_contracts(tmp_path)

    assert [path.relative_to(tmp_path).as_posix() for path in written] == EXPECTED_FILES
    for path in written:
        assert json.loads(path.read_text(encoding="utf-8"))


def test_exported_examples_validate_against_contract_models(tmp_path: Path) -> None:
    export_contracts(tmp_path)

    examples = {
        "module.json": ModuleManifest,
        "job.json": JobRequest,
        "result.json": ModuleResult,
    }
    for filename, model in examples.items():
        payload = json.loads(
            (tmp_path / "contracts" / "examples" / filename).read_text(encoding="utf-8")
        )
        model.model_validate(payload)


def test_export_contracts_is_deterministic(tmp_path: Path) -> None:
    first_paths = export_contracts(tmp_path)
    first_contents = {path: path.read_bytes() for path in first_paths}

    second_paths = export_contracts(tmp_path)

    assert second_paths == first_paths
    assert {path: path.read_bytes() for path in second_paths} == first_contents
