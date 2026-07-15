import json
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"
CANONICAL_SCHEMA = ROOT / "contracts" / "schemas" / "module-manifest.schema.json"


def test_manifest_matches_canonical_schema() -> None:
    manifest = json.loads((MODULE_ROOT / "module.json").read_text(encoding="utf-8"))
    schema = json.loads(CANONICAL_SCHEMA.read_text(encoding="utf-8"))

    jsonschema.validate(manifest, schema)
    assert manifest == {
        "schema_version": "1.0",
        "module_id": "moisture",
        "module_name": "竹丝水分检测",
        "module_version": "0.1.0",
        "entrypoint": "run_module.bat",
        "supported_extensions": [".xlsx"],
        "supports_single_file": True,
        "supports_batch": True,
        "supports_incremental": False,
        "requires_network": False,
    }


def test_manifest_entrypoint_and_minimum_package_exist() -> None:
    for relative_path in (
        "run_module.bat",
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
