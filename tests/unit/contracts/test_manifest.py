import pytest
from pydantic import ValidationError

from core.contracts.enums import ModuleId, Severity, TaskStatus
from core.contracts.manifest import ModuleManifest


def test_manifest_accepts_canonical_mock_module() -> None:
    manifest = ModuleManifest.model_validate(
        {
            "schema_version": "1.0",
            "module_id": "moisture",
            "module_name": "原竹丝水分检测",
            "module_version": "0.1.0",
            "entrypoint": "run_module.bat",
            "management_entrypoint": "run_management.bat",
            "capabilities": ["ai_report"],
            "supported_extensions": [".xlsx"],
            "supports_single_file": True,
            "supports_batch": True,
            "supports_incremental": True,
            "requires_network": False,
        }
    )
    assert manifest.module_id is ModuleId.MOISTURE
    assert manifest.capabilities == ["ai_report"]
    assert Severity.WARNING.value == "warning"
    assert TaskStatus.NEEDS_CONFIRMATION.value == "needs_confirmation"


def test_manifest_rejects_non_semantic_version() -> None:
    with pytest.raises(ValidationError):
        ModuleManifest.model_validate(
            {
                "schema_version": "1.0",
                "module_id": "moisture",
                "module_name": "x",
                "module_version": "latest",
                "entrypoint": "run_module.bat",
                "supported_extensions": [".xlsx"],
                "supports_single_file": True,
                "supports_batch": True,
                "supports_incremental": False,
                "requires_network": False,
            }
        )
