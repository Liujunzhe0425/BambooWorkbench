from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from moisture.adapters.rules import package_loader
from moisture.adapters.rules.package_loader import (
    RulePackageIntegrityError,
    RulePackageLoader,
    RulePackageValidationError,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rule_packages"
ACTIVE = Path(__file__).parents[3] / "rules" / "active"


def test_default_schema_uses_runtime_module_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(package_loader, "runtime_module_root", lambda: tmp_path)

    loader = RulePackageLoader()

    assert loader.schema_path == tmp_path / "schemas" / "rule-package.schema.json"


def test_loader_validates_exact_rules_file_bytes_and_freezes_snapshot() -> None:
    package_dir = FIXTURES / "valid"
    snapshot = RulePackageLoader().load(package_dir)
    expected = hashlib.sha256((package_dir / "rules.yaml").read_bytes()).hexdigest()

    assert snapshot.rules_sha256 == expected
    assert snapshot.content_hash == expected
    assert snapshot.customer_confirmation_status == "confirmed"
    assert snapshot.definitions[0].customer_confirmation_status == "confirmed"
    with pytest.raises(FrozenInstanceError):
        snapshot.package_id = "changed"  # type: ignore[misc]


def test_loader_rejects_rule_bytes_that_do_not_match_manifest(tmp_path: Path) -> None:
    source = FIXTURES / "valid"
    (tmp_path / "rule-package.json").write_bytes((source / "rule-package.json").read_bytes())
    (tmp_path / "rules.yaml").write_bytes((source / "rules.yaml").read_bytes() + b"\n# tampered\n")

    with pytest.raises(RulePackageIntegrityError, match="SHA-256"):
        RulePackageLoader().load(tmp_path)


def test_loader_rejects_invalid_manifest_and_unsafe_rules_path(tmp_path: Path) -> None:
    manifest = json.loads((FIXTURES / "valid" / "rule-package.json").read_text(encoding="utf-8"))
    manifest["rules_file"] = "../outside.yaml"
    (tmp_path / "rule-package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "rules.yaml").write_text("definitions: []\n", encoding="utf-8")

    with pytest.raises(RulePackageValidationError):
        RulePackageLoader().load(tmp_path)


def test_default_rules_are_formally_approved_for_bamboo_materials() -> None:
    snapshot = RulePackageLoader().load(ACTIVE)

    assert snapshot.customer_confirmation_status == "confirmed"
    assert {rule.rule_id: str(rule.threshold) for rule in snapshot.definitions} == {
        "HIGH_DEFAULT": "0.55",
        "LOW_DEFAULT": "0.47",
        "RANGE_VALUE_HIGH": "0.13",
    }
    assert all(
        rule.customer_confirmation_status == "confirmed" for rule in snapshot.definitions
    )
    assert all(
        set(rule.applicable_materials) == {"竹丝", "原竹丝"}
        for rule in snapshot.definitions
    )
    assert {path.name for path in ACTIVE.iterdir()} == {
        "rule-package.json",
        "rules.yaml",
    }
    assert (FIXTURES / "valid" / "expected-results.json").is_file()
