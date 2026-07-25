from types import SimpleNamespace

from core.contracts.enums import ModuleId
from core.tasks.service import TaskService


class _Management:
    def execute_sync(self, module_id, operation, parameters):
        assert module_id is ModuleId.MOISTURE
        assert operation == "get_active_rule_identity"
        assert parameters == {}
        return {
            "status": "ok",
            "result": {"active_rule": {"version": "rules-v1", "sha256": "a" * 64}},
        }


def test_rule_snapshot_is_injected_without_overwriting_business_config() -> None:
    service = TaskService.__new__(TaskService)
    service.module_management_service = _Management()
    module = SimpleNamespace(
        manifest=SimpleNamespace(capabilities=["rule_snapshot"])
    )

    configured = service._with_rule_snapshot(
        ModuleId.MOISTURE,
        module,
        {"schema_version": "1.0", "operation": "ai_report"},
    )

    assert configured == {
        "schema_version": "1.0",
        "operation": "ai_report",
        "rule_selection": {"version": "rules-v1", "sha256": "a" * 64},
    }
