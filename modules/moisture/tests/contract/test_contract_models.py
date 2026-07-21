import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[4]
MODULE_ROOT = ROOT / "modules" / "moisture"
RESULT_SCHEMA = ROOT / "contracts" / "schemas" / "module-result.schema.json"


def _contract_api():
    sys.path.insert(0, str(MODULE_ROOT / "src"))
    try:
        from moisture.contract.validators import (
            ContractValidationError,
            validate_job_payload,
            validate_result_payload,
        )
    finally:
        sys.path.pop(0)
    return ContractValidationError, validate_job_payload, validate_result_payload


def _job_payload(tmp_path: Path, **overrides: object) -> dict[str, object]:
    input_file = tmp_path / "input.xlsx"
    input_file.write_bytes(b"contract model input")
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "t04-current-001",
        "module_id": "moisture",
        "phase": "draft",
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
    }
    payload.update(overrides)
    return payload


def _result_payload(tmp_path: Path, **overrides: object) -> dict[str, object]:
    source_file = str((tmp_path / "input.xlsx").resolve())
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "t04-current-001",
        "module_id": "moisture",
        "module_version": "0.1.0",
        "status": "success",
        "rule_version": None,
        "summary": {
            "input_count": 1,
            "processed_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 1,
            "confirmation_count": 0,
        },
        "anomalies": [
            {
                "anomaly_id": "a-1",
                "severity": "info",
                "field": "moisture",
                "value": Decimal("0.5500"),
                "rule_id": None,
                "message": "deterministic screening",
                "suggestion": None,
                "source": {
                    "source_file": source_file,
                    "sheet": "Sheet1",
                    "cell_or_range": "A1",
                },
            }
        ],
        "confirmations": [],
        "outputs": [],
        "file_results": [],
        "service_requests": [],
        "analysis_summary": None,
        "errors": [],
        "started_at": "2026-07-16T08:00:00+08:00",
        "finished_at": "2026-07-16T08:00:01+08:00",
    }
    payload.update(overrides)
    return payload


def test_job_request_preserves_current_and_parent_job_ids(tmp_path: Path) -> None:
    _, validate_job_payload, _ = _contract_api()
    confirmation_file = tmp_path / "confirmations.json"
    confirmation_file.write_text("{}", encoding="utf-8")
    payload = _job_payload(
        tmp_path,
        job_id="t04-finalize-002",
        phase="finalize",
        parent_job_id="t04-draft-001",
        confirmation_file=str(confirmation_file.resolve()),
    )

    job = validate_job_payload(payload)

    assert job.job_id == "t04-finalize-002"
    assert job.parent_job_id == "t04-draft-001"
    assert job.root_job_id == "t04-draft-001"
    assert isinstance(job.input_files[0], Path)
    assert isinstance(job.output_dir, Path)
    with pytest.raises((AttributeError, TypeError)):
        job.job_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "replacement",
    [
        {"extra": "forbidden"},
        {"ai_enabled": 1},
        {"input_files": "not-a-list"},
        {"phase": "finalize", "parent_job_id": None},
    ],
)
def test_job_request_rejects_unknown_types_and_invalid_conditions(
    tmp_path: Path, replacement: dict[str, object]
) -> None:
    ContractValidationError, validate_job_payload, _ = _contract_api()
    payload = _job_payload(tmp_path)
    payload.update(replacement)

    with pytest.raises(ContractValidationError) as caught:
        validate_job_payload(payload)

    assert caught.value.code.startswith("CONTRACT_")
    assert "jsonschema" not in str(caught.value).lower()


def test_result_model_preserves_decimal_paths_and_times(tmp_path: Path) -> None:
    _, _, validate_result_payload = _contract_api()

    result = validate_result_payload(_result_payload(tmp_path))

    assert result.anomalies[0].value == Decimal("0.5500")
    assert isinstance(result.anomalies[0].value, Decimal)
    assert isinstance(result.anomalies[0].source.source_file, Path)
    assert isinstance(result.started_at, datetime)
    assert result.started_at.utcoffset() is not None


def test_result_model_is_strict_at_nested_boundaries(tmp_path: Path) -> None:
    ContractValidationError, _, validate_result_payload = _contract_api()
    payload = _result_payload(tmp_path)
    payload["summary"] = {**payload["summary"], "unknown": 1}  # type: ignore[arg-type]

    with pytest.raises(ContractValidationError) as caught:
        validate_result_payload(payload)

    assert caught.value.code == "CONTRACT_SCHEMA_INVALID"
    assert "summary" in caught.value.field


def test_result_payload_round_trips_through_official_schema(tmp_path: Path) -> None:
    _, _, validate_result_payload = _contract_api()
    result = validate_result_payload(_result_payload(tmp_path))
    serialized = result.to_payload()
    schema = json.loads(RESULT_SCHEMA.read_text(encoding="utf-8"))

    jsonschema.validate(serialized, schema, format_checker=jsonschema.FormatChecker())
    assert serialized["anomalies"][0]["value"] == 0.55
    assert serialized["anomalies"][0]["source"]["source_file"].endswith("input.xlsx")


def test_needs_confirmation_semantics_match_official_contract_model(
    tmp_path: Path,
) -> None:
    ContractValidationError, _, validate_result_payload = _contract_api()
    payload = _result_payload(
        tmp_path,
        status="needs_confirmation",
        summary={
            "input_count": 1,
            "processed_count": 1,
            "skipped_count": 0,
            "failed_count": 0,
            "anomaly_count": 1,
            "confirmation_count": 0,
        },
    )

    with pytest.raises(ContractValidationError) as caught:
        validate_result_payload(payload)

    assert caught.value.code == "CONTRACT_SEMANTIC_INVALID"
