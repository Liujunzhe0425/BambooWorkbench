import json
import tomllib
from pathlib import Path

from core.contracts.manifest import ModuleManifest
from core.contracts.validator import validate_module

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"


def test_manifest_matches_framework_contract() -> None:
    manifest = json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))

    parsed = ModuleManifest.model_validate(manifest)
    report = validate_module(MODULE_ROOT)

    assert report.ok, report.issues
    assert parsed.management_contract is not None
    assert manifest == {
        "schema_version": "1.0",
        "module_id": "moisture",
        "module_name": "竹丝水分检测",
        "module_version": "1.3.2",
        "entrypoint": "run_module.bat",
        "management_entrypoint": "run_management.bat",
        "management_contract": {
            "schema_version": "1.1",
            "request_schema": "schemas/moisture-management-request.schema.json",
            "response_schema": "schemas/moisture-management-response.schema.json",
        },
        "capabilities": [
            "ai_report",
            "experience_management",
            "rule_management",
            "rule_snapshot",
            "monthly_rollup",
        ],
        "monthly_rollup": {
            "schema_version": "1.0",
            "entrypoint": "run_module.bat",
            "snapshot_schema": "schemas/moisture-monthly-snapshot.schema.json",
            "request_schema": (
                "schemas/moisture-monthly-rollup-public-request.schema.json"
            ),
            "response_schema": (
                "schemas/moisture-monthly-rollup-public-response.schema.json"
            ),
            "learning_schema": "schemas/moisture-learning-public.schema.json",
        },
        "supported_extensions": [".xlsx"],
        "supports_single_file": True,
        "supports_batch": True,
        "supports_incremental": True,
        "requires_network": False,
    }


def test_management_contract_schema_assets_exist() -> None:
    manifest = ModuleManifest.model_validate_json(
        (MODULE_ROOT / "module.json").read_text(encoding="utf-8")
    )
    contract = manifest.management_contract

    assert contract is not None
    assert contract.schema_version == "1.1"
    assert (MODULE_ROOT / contract.request_schema).is_file()
    assert (MODULE_ROOT / contract.response_schema).is_file()


def test_monthly_rollup_contract_schema_assets_exist() -> None:
    manifest = ModuleManifest.model_validate_json(
        (MODULE_ROOT / "module.json").read_text(encoding="utf-8")
    )
    contract = manifest.monthly_rollup

    assert contract is not None
    assert contract.schema_version == "1.0"
    assert "monthly_rollup" in manifest.capabilities
    for relative_path in (
        contract.snapshot_schema,
        contract.request_schema,
        contract.response_schema,
        contract.learning_schema,
    ):
        assert relative_path is not None
        assert (MODULE_ROOT / relative_path).is_file()


def test_manifest_entrypoint_and_minimum_package_exist() -> None:
    for relative_path in (
        "run_module.bat",
        "run_management.bat",
        "README.md",
        "CHANGELOG.md",
        "requirements.txt",
        "pyproject.toml",
        "samples/README.md",
        "src/moisture/__init__.py",
        "src/moisture/cli.py",
        "src/moisture/infrastructure/diagnostics.py",
    ):
        assert (MODULE_ROOT / relative_path).is_file(), relative_path


def test_runtime_dependencies_are_declared_consistently() -> None:
    expected = [
        "jsonschema>=4.23,<5",
        "PyYAML>=6,<7",
        "openpyxl>=3.1,<4",
        "XlsxWriter>=3.2,<4",
        "Jinja2>=3.1,<4",
    ]
    requirements = [
        line.strip()
        for line in (MODULE_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pyproject = tomllib.loads(
        (MODULE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert requirements == expected
    assert pyproject["project"]["dependencies"] == expected


def test_readme_documents_schema_validation_dependency() -> None:
    readme = (MODULE_ROOT / "README.md").read_text(encoding="utf-8")

    assert "没有第三方运行时依赖" not in readme
    assert (
        "`jsonschema` 是模块的 Schema 校验依赖；紧随其后的 "
        "`requirements.txt` 安装命令会安装该依赖。"
    ) in readme
