from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

MODULE_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.adapters.rules import data_root  # noqa: E402
from moisture.adapters.rules.data_root import (  # noqa: E402
    ManagedRuleError,
    load_runtime_rule_snapshot,
)
from moisture.adapters.rules.local_editable_repository import (  # noqa: E402
    LocalEditableRuleRepository,
    RuleAdminConflictError,
    RuleAdminValidationError,
)


def _manifest(version: str, *, confirmed: bool = True) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "package_id": f"moisture-{version}",
        "rule_version": version,
        "rules_file": "rules.yaml",
        "rules_sha256": "0" * 64,
        "source": "synthetic governance test",
        "applicable_scope": "原竹丝；全年",
        "customer_confirmation_status": (
            "confirmed" if confirmed else "pending_confirmation"
        ),
        "released_at": "2026-07-24T00:00:00+08:00",
        "module_version": "1.0.1",
    }


def _rules(
    threshold: str = "0.54",
    *,
    field: str = "total_average",
    confirmed: bool = True,
) -> str:
    status = "confirmed" if confirmed else "pending_confirmation"
    return f"""definitions:
  - rule_id: TEST_HIGH
    rule_type: numeric_threshold
    field: {field}
    operator: ">"
    threshold: "{threshold}"
    color: orange
    applicable_materials: [原竹丝]
    applicable_seasons: [all]
    customer_confirmation_status: {status}
"""


def test_draft_publish_history_copy_retire_and_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "module-data"
    monkeypatch.setenv("BAMBOO_MOISTURE_DATA_DIR", str(data_dir))
    repository = LocalEditableRuleRepository(data_dir / "rules")
    baseline = repository.list_current()[0]

    draft = repository.create_draft(_manifest("managed-v1"), _rules())
    assert repository.list_current()[0] == baseline
    assert repository.list_drafts()[0].rule_version == "managed-v1"
    with pytest.raises(ManagedRuleError):
        load_runtime_rule_snapshot(
            rule_version=draft.rule_version,
            rules_sha256=draft.rules_sha256,
        )

    published = repository.publish("managed-v1", draft.package_hash)
    assert repository.list_current()[0].rule_version == "managed-v1"
    assert load_runtime_rule_snapshot().rules_sha256 == published.rules_sha256
    assert {item.rule_version for item in repository.list_history()} == {
        baseline.rule_version
    }

    copied = repository.copy_history_to_draft(
        baseline.rule_version,
        repository.list_history()[0].package_hash,
        "managed-v2",
    )
    assert copied.rule_version == "managed-v2"
    assert copied.rules_sha256 == baseline.rules_sha256

    retired = repository.retire_current(published.rules_sha256)
    assert retired.lifecycle == "retired"
    assert repository.list_current() == []
    with pytest.raises(ManagedRuleError, match="no active"):
        load_runtime_rule_snapshot()

    restored = repository.restore("managed-v1", published.rules_sha256)
    assert restored.lifecycle == "current"
    assert load_runtime_rule_snapshot().rule_version == "managed-v1"


def test_hash_conflict_pending_publish_and_unknown_field_are_rejected(
    tmp_path: Path,
) -> None:
    repository = LocalEditableRuleRepository(tmp_path / "rules")
    draft = repository.create_draft(
        _manifest("pending-v1", confirmed=False),
        _rules(confirmed=False),
    )
    with pytest.raises(RuleAdminConflictError, match="expected package hash"):
        repository.update_draft(
            "pending-v1",
            _manifest("pending-v1", confirmed=False),
            _rules("0.53", confirmed=False),
            "a" * 64,
        )
    with pytest.raises(RuleAdminValidationError, match="explicitly confirmed"):
        repository.publish("pending-v1", draft.package_hash)
    with pytest.raises(RuleAdminValidationError, match="unsupported numeric field"):
        repository.create_draft(
            _manifest("bad-field-v1"),
            _rules(field="unknown_metric"),
        )


def test_pointer_failure_preserves_old_active_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = LocalEditableRuleRepository(tmp_path / "rules")
    old = repository.list_current()[0]
    draft = repository.create_draft(_manifest("atomic-v1"), _rules())
    original_replace = data_root.os.replace

    def fail_pointer(source, target):
        if Path(target).name == "active.json":
            raise OSError("synthetic pointer failure")
        return original_replace(source, target)

    monkeypatch.setattr(data_root.os, "replace", fail_pointer)
    with pytest.raises(OSError, match="synthetic pointer failure"):
        repository.publish("atomic-v1", draft.package_hash)

    pointer = json.loads(
        (tmp_path / "rules" / "active.json").read_text(encoding="utf-8")
    )
    assert pointer["active"]["rule_version"] == old.rule_version
    assert repository.list_current()[0].rules_sha256 == old.rules_sha256
    assert repository.list_drafts()[0].rule_version == "atomic-v1"
