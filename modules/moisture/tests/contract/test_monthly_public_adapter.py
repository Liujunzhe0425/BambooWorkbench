from __future__ import annotations

# ruff: noqa: E402, I001

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from core.contracts.monthly import MonthlyRollupRequest, MonthlyRollupResult
from core.contracts.result import LearningDescriptor
from moisture.application.confirmation_builder import build_confirmations
from moisture.application.monthly_public_adapter import run_public_monthly_rollup
from moisture.domain.models import BusinessConfirmationIssue

SCHEMAS = MODULE_ROOT / "schemas"
SNAPSHOT_FIXTURE = (
    MODULE_ROOT / "tests" / "fixtures" / "monthly" / "snapshot-example.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _public_request(tmp_path: Path) -> tuple[Path, Path]:
    snapshot_root = tmp_path / "snapshots"
    snapshot_root.mkdir()
    snapshot_path = snapshot_root / "month-04.json"
    snapshot_path.write_bytes(SNAPSHOT_FIXTURE.read_bytes())
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    payload = {
        "schema_version": "1.0",
        "transaction_id": "txn-public-0001",
        "module_id": "moisture",
        "module_version": "1.3.5",
        "year": 2026,
        "target_month": 4,
        "snapshots": [
            {
                "snapshot_id": "snapshot-public-0001",
                "job_id": "job-public-0001",
                "module_id": "moisture",
                "year": 2026,
                "month": 4,
                "path": str(snapshot_path.resolve()),
                "size": snapshot_path.stat().st_size,
                "sha256": _sha256(snapshot_path),
            }
        ],
        "snapshot_root": str(snapshot_root.resolve()),
        "output_dir": str(output_dir.resolve()),
        "configuration_identity": {
            "version": "default-v2-approved",
            "sha256": "a" * 64,
        },
        "offline_required": True,
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    return request_path.resolve(), (output_dir / "rollup-result.json").resolve()


def test_public_rollup_schemas_are_exact_framework_shapes() -> None:
    request_schema = json.loads(
        (SCHEMAS / "moisture-monthly-rollup-public-request.schema.json").read_text(
            encoding="utf-8"
        )
    )
    response_schema = json.loads(
        (SCHEMAS / "moisture-monthly-rollup-public-response.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(request_schema)
    Draft202012Validator.check_schema(response_schema)
    assert request_schema == MonthlyRollupRequest.model_json_schema()
    assert response_schema == MonthlyRollupResult.model_json_schema()


def test_public_rollup_adapter_renders_and_acknowledges_framework_identity(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    request_path, response_path = _public_request(tmp_path)
    monkeypatch.setenv("BAMBOO_OFFLINE", "1")

    assert run_public_monthly_rollup(request_path, response_path) == 0

    payload = json.loads(response_path.read_text(encoding="utf-8"))
    result = MonthlyRollupResult.model_validate(payload)
    assert result.transaction_id == "txn-public-0001"
    assert result.module_version == "1.3.5"
    assert result.used_months == [4]
    assert result.network_call_count == 0
    assert result.record_count == 1
    assert [item.month for item in result.snapshot_hashes] == [4]
    assert all(Path(item.path).is_absolute() for item in result.outputs)
    progress = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    assert [event["percent"] for event in progress] == [0, 100]
    assert all("source_file" not in event for event in progress)


def test_real_bat_rollup_works_outside_repository_directory(
    tmp_path: Path,
) -> None:
    request_path, response_path = _public_request(tmp_path)
    environment = os.environ.copy()
    environment["BAMBOO_OFFLINE"] = "1"
    environment["BAMBOO_MODULE_PYTHON"] = sys.executable

    completed = subprocess.run(
        [
            "cmd.exe",
            "/d",
            "/c",
            str((MODULE_ROOT / "run_module.bat").resolve()),
            "rollup",
            "--request",
            str(request_path),
            "--response",
            str(response_path),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = MonthlyRollupResult.model_validate_json(
        response_path.read_text(encoding="utf-8")
    )
    assert result.status == "success"
    assert result.network_call_count == 0
    assert all(
        json.loads(line)["type"] == "progress"
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def test_public_rollup_adapter_writes_stable_failure_envelope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    request_path, response_path = _public_request(tmp_path)
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    payload["configuration_identity"]["sha256"] = "b" * 64
    request_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("BAMBOO_OFFLINE", "1")

    assert run_public_monthly_rollup(request_path, response_path) == 3

    result = MonthlyRollupResult.model_validate_json(
        response_path.read_text(encoding="utf-8")
    )
    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "monthly_rollup_snapshot_invalid"
    assert result.outputs == []
    assert result.network_call_count == 0


def test_public_learning_mapping_is_framework_valid_and_can_be_disabled(
    tmp_path: Path,
) -> None:
    issue = BusinessConfirmationIssue(
        kind="supplier_mapping",
        fingerprint="a" * 64,
        field="supplier",
        candidates=("supplier-alpha", "supplier-beta"),
        suggested_value="supplier-beta",
        source_file=tmp_path / "source.xlsx",
    )
    prompt = build_confirmations("draft-root", (issue,))[0]
    learning = LearningDescriptor.model_validate(prompt["learning"])
    schema = json.loads(
        (SCHEMAS / "moisture-learning-public.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator(schema).validate(prompt["learning"])

    assert learning.field == "supplier"
    assert learning.base_suggestion_id in {
        candidate.candidate_id for candidate in learning.candidates
    }
    assert learning.context_levels == [
        ["field", "material_category", "source_category"],
        ["field", "material_category"],
        ["field"],
    ]
    assert "learning" not in build_confirmations(
        "draft-root",
        (issue,),
        learning_enabled=False,
    )[0]
