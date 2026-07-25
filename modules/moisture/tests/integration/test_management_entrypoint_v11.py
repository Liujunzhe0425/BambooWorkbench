from __future__ import annotations

import json
import os
import subprocess
import sys
from itertools import count
from pathlib import Path

import yaml

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))
sys.path.insert(0, str(MODULE_ROOT / "tests"))

from moisture.application.draft_orchestrator import run_draft  # noqa: E402
from moisture.contract.job_models import (  # noqa: E402
    JobPhase,
    JobRequest,
    ModuleId,
    RunMode,
)
from moisture.contract.management import OPERATIONS  # noqa: E402

ENTRYPOINT = MODULE_ROOT / "run_management.bat"
_REQUEST_IDS = count()
pytest_plugins = ("fixtures.workbooks.workbook_factory",)


def _call(
    tmp_path: Path,
    data_dir: Path,
    operation: str,
    parameters: dict[str, object] | None = None,
    *,
    authorized_data_dir: Path | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    workspace = tmp_path / f"process-{next(_REQUEST_IDS):03d}-{operation}"
    workspace.mkdir()
    request_path = (workspace / "request.json").resolve()
    response_path = (workspace / "response.json").resolve()
    request = {
        "schema_version": "1.1",
        "request_id": f"request-{next(_REQUEST_IDS):06d}",
        "module_id": "moisture",
        "operation": operation,
        "data_dir": str(data_dir.resolve()),
        "parameters": parameters or {},
    }
    request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
    environment = os.environ.copy()
    environment["BAMBOO_MODULE_PYTHON"] = sys.executable
    environment["BAMBOO_MOISTURE_DATA_DIR"] = str(
        (authorized_data_dir or data_dir).resolve()
    )
    completed = subprocess.run(
        [
            str(ENTRYPOINT),
            "manage",
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    response = (
        json.loads(response_path.read_text(encoding="utf-8"))
        if response_path.exists()
        else {}
    )
    return completed, response


def _ok(
    tmp_path: Path,
    data_dir: Path,
    operation: str,
    parameters: dict[str, object] | None = None,
) -> dict[str, object]:
    completed, response = _call(tmp_path, data_dir, operation, parameters)
    assert completed.returncode == 0, (operation, completed.stderr, response)
    assert response["status"] == "ok", (operation, response)
    events = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [event["percent"] for event in events] == [0, 100]
    assert "Traceback" not in completed.stderr
    return response["result"]


def _summary(tmp_path: Path, workbook_factory) -> Path:
    source = workbook_factory(
        tmp_path / "raw.xlsx",
        moisture_values=(0.50,),
        mass_values=((100, 50, 0),),
        material_type="原竹丝",
        arrival_date="2026-07-01",
        test_date="2026-07-02",
    )
    output = tmp_path / "summary-output"
    job = JobRequest(
        schema_version="1.0",
        job_id="management-v11-summary",
        module_id=ModuleId.MOISTURE,
        phase=JobPhase.DRAFT,
        run_mode=RunMode.SINGLE,
        input_files=(source,),
        output_dir=output,
    )
    assert run_draft(job) == 0
    return output / "moisture_summary.xlsx"


def _experience_document(
    *,
    version: str = "1.0.0",
    status: str = "draft",
    body: str = "脱敏经验指导",
) -> str:
    payload = {
        "experience_id": "EXP-PROCESS-001",
        "version": version,
        "status": status,
        "title": "公开进程经验",
        "source": "synthetic/process",
        "applicable_suppliers": ["*"],
        "applicable_materials": ["原竹丝"],
        "applicable_seasons": ["*"],
        "applicable_metrics": ["total_average"],
        "author": "synthetic-author",
        "reviewer": "synthetic-reviewer",
        "evidence_sources": ["synthetic/process"],
        "effective_at": "2026-07-24T00:00:00+08:00",
        "supersedes": None if version == "1.0.0" else "1.0.0",
    }
    rendered = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    return f"---\n{rendered}---\n{body}\n"


def _rule_manifest(version: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "package_id": f"process-{version}",
        "rule_version": version,
        "rules_file": "rules.yaml",
        "rules_sha256": "0" * 64,
        "source": "synthetic public management process",
        "applicable_scope": "原竹丝；全年",
        "customer_confirmation_status": "confirmed",
        "released_at": "2026-07-24T00:00:00+08:00",
        "module_version": "1.1.1",
    }


def _rules(threshold: str) -> str:
    return f"""definitions:
  - rule_id: PUBLIC_PROCESS_HIGH
    rule_type: numeric_threshold
    field: total_average
    operator: ">"
    threshold: "{threshold}"
    color: orange
    applicable_materials: [原竹丝]
    applicable_seasons: [all]
    customer_confirmation_status: confirmed
"""


def test_all_27_public_operations_run_through_real_bat(
    tmp_path: Path, workbook_factory
) -> None:
    data_dir = tmp_path / "module-data"
    data_dir.mkdir()
    source = _summary(tmp_path, workbook_factory)
    called: set[str] = set()

    def call(
        operation: str, parameters: dict[str, object] | None = None
    ) -> dict[str, object]:
        called.add(operation)
        return _ok(tmp_path, data_dir, operation, parameters)

    imported = call(
        "import_history_summary", {"input_file": str(source.resolve())}
    )
    history_id = str(imported["imported_history_id"])
    assert len(call("list_history_summaries")["history_items"]) == 1
    assert call("list_approved_experiences")["experience_items"]

    document = _experience_document()
    assert call("list_experience_drafts")["experience_items"] == []
    assert call("list_experience_approved")["experience_items"]
    assert call("list_experience_history")["experience_items"] == []
    validated = call(
        "validate_experience_draft", {"document": document}
    )["experience"]
    assert validated["status"] == "draft"
    created = call(
        "create_experience_draft", {"document": document}
    )["experience"]
    shown = call(
        "show_experience",
        {"experience_id": "EXP-PROCESS-001", "version": "1.0.0"},
    )["experience"]
    assert shown["sha256"] == created["sha256"]
    updated = call(
        "update_experience_draft",
        {
            "experience_id": "EXP-PROCESS-001",
            "version": "1.0.0",
            "expected_hash": created["sha256"],
            "document": _experience_document(body="更新后的脱敏经验"),
        },
    )["experience"]
    approved = call(
        "publish_experience",
        {
            "experience_id": "EXP-PROCESS-001",
            "version": "1.0.0",
            "expected_hash": updated["sha256"],
        },
    )["experience"]
    retired = call(
        "retire_experience",
        {
            "experience_id": "EXP-PROCESS-001",
            "version": "1.0.0",
            "expected_hash": approved["sha256"],
        },
    )["experience"]
    copied = call(
        "copy_experience_history_to_draft",
        {
            "experience_id": "EXP-PROCESS-001",
            "version": "1.0.0",
            "expected_hash": retired["sha256"],
            "new_version": "2.0.0",
        },
    )["experience"]
    assert copied["status"] == "draft"

    active = call("get_active_rule_identity")["active_rule"]
    assert active == {
        "version": call("list_current_rules")["rule_items"][0]["rule_version"],
        "sha256": call("list_current_rules")["rule_items"][0]["rules_sha256"],
    }
    assert call("list_rule_drafts")["rule_items"] == []
    call("list_rule_history")
    draft = call(
        "create_rule_draft",
        {"manifest": _rule_manifest("rules-v2"), "rules_yaml": _rules("0.55")},
    )["rule"]
    package = call(
        "show_rule_package", {"rule_version": "rules-v2"}
    )["rule_package"]
    assert package["package_hash"] == draft["package_hash"]
    assert call(
        "validate_rule_draft", {"rule_version": "rules-v2"}
    )["rule"]["lifecycle"] == "draft"
    preview = call(
        "preview_rule_draft",
        {"rule_version": "rules-v2", "history_ids": [history_id]},
    )["rule_preview"]
    assert preview["batch_count"] >= 1
    updated_rule = call(
        "update_rule_draft",
        {
            "rule_version": "rules-v2",
            "expected_package_hash": draft["package_hash"],
            "manifest": _rule_manifest("rules-v2"),
            "rules_yaml": _rules("0.56"),
        },
    )["rule"]
    published = call(
        "publish_rule",
        {
            "rule_version": "rules-v2",
            "expected_package_hash": updated_rule["package_hash"],
        },
    )["rule"]
    assert call("get_active_rule_identity")["active_rule"] == {
        "version": published["rule_version"],
        "sha256": published["rules_sha256"],
    }
    history = call("list_rule_history")["rule_items"]
    baseline = next(item for item in history if item["rule_version"] != "rules-v2")
    retired_rule = call(
        "retire_current_rule",
        {"expected_rules_sha256": published["rules_sha256"]},
    )["rule"]
    restored = call(
        "restore_rule_version",
        {
            "rule_version": retired_rule["rule_version"],
            "expected_rules_sha256": retired_rule["rules_sha256"],
        },
    )["rule"]
    assert restored["lifecycle"] == "current"
    copied_rule = call(
        "copy_rule_history_to_draft",
        {
            "rule_version": baseline["rule_version"],
            "expected_package_hash": baseline["package_hash"],
            "new_version": "rules-copy-v3",
        },
    )["rule"]
    assert copied_rule["lifecycle"] == "draft"

    retired_history = call(
        "retire_history_summary", {"history_id": history_id}
    )["history_item"]
    assert retired_history["active"] is False
    assert called == set(OPERATIONS)


def test_v11_errors_are_stable_redacted_and_path_safe(tmp_path: Path) -> None:
    data_dir = tmp_path / "module-data"
    data_dir.mkdir()
    document = _experience_document()
    created = _ok(
        tmp_path,
        data_dir,
        "create_experience_draft",
        {"document": document},
    )["experience"]

    completed, response = _call(
        tmp_path,
        data_dir,
        "publish_experience",
        {
            "experience_id": "EXP-PROCESS-001",
            "version": "1.0.0",
            "expected_hash": "0" * 64,
        },
    )
    assert completed.returncode == 0
    assert response["error_code"] == "EXPERIENCE_HASH_CONFLICT"
    assert str(tmp_path) not in json.dumps(response, ensure_ascii=False)
    assert "Traceback" not in completed.stderr
    assert created["sha256"] != "0" * 64

    completed, response = _call(
        tmp_path,
        data_dir,
        "show_experience",
        {"experience_id": "../escape", "version": "1.0.0"},
    )
    assert completed.returncode == 2
    assert response == {}
    assert "Traceback" not in completed.stderr

    other = tmp_path / "other-data"
    other.mkdir()
    completed, response = _call(
        tmp_path,
        data_dir,
        "list_rule_drafts",
        authorized_data_dir=other,
    )
    assert completed.returncode == 0
    assert response["error_code"] == "MANAGEMENT_PATH_REJECTED"
    assert str(data_dir) not in json.dumps(response, ensure_ascii=False)


def test_corrupt_rule_directory_fails_without_fallback(tmp_path: Path) -> None:
    data_dir = tmp_path / "module-data"
    rules = data_dir / "rules"
    rules.mkdir(parents=True)
    (rules / "active.json").write_text("{}", encoding="utf-8")

    completed, response = _call(
        tmp_path,
        data_dir,
        "get_active_rule_identity",
    )

    assert completed.returncode == 0
    assert response["status"] == "error"
    assert response["error_code"] == "MANAGEMENT_DATA_CORRUPTED"
    assert str(tmp_path) not in json.dumps(response, ensure_ascii=False)
    assert "Traceback" not in completed.stderr
