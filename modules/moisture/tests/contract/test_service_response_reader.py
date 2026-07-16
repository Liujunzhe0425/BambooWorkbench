# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.contract.service_response_reader import read_service_responses


def _write_envelope(path: Path, responses: list[dict[str, object]]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "task_id": "draft-job-001",
                "module_id": "moisture",
                "responses": responses,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def test_service_response_reader_preserves_provider_status(tmp_path: Path) -> None:
    path = _write_envelope(
        tmp_path / "service-response.json",
        [
            {
                "request_id": "ai-denied",
                "service": "ai",
                "status": "denied",
                "text": None,
            },
            {
                "request_id": "ai-error",
                "service": "ai",
                "status": "error",
                "text": None,
                "error": "provider unavailable",
            },
            {
                "request_id": "ai-timeout",
                "service": "ai",
                "status": "timeout",
                "text": None,
                "error": "deadline exceeded",
            },
        ],
    )

    result = read_service_responses(
        path,
        root_job_id="draft-job-001",
        expected_requests={
            "ai-denied": "ai",
            "ai-error": "ai",
            "ai-timeout": "ai",
        },
    )

    assert result.errors == ()
    assert result.envelope is not None
    assert [response.status for response in result.envelope.responses] == [
        "denied",
        "error",
        "timeout",
    ]
    assert result.envelope.responses[1].error == "provider unavailable"
    assert result.envelope.responses[2].text is None


def test_service_reader_preserves_text_and_knowledge_items(tmp_path: Path) -> None:
    path = _write_envelope(
        tmp_path / "service-response.json",
        [
            {
                "request_id": "ai-001",
                "service": "ai",
                "status": "ok",
                "text": "local provider result",
            },
            {
                "request_id": "knowledge-001",
                "service": "knowledge",
                "status": "ok",
                "items": [{"record_id": "rule-1", "title": "复核规则"}],
            },
        ],
    )

    result = read_service_responses(
        path,
        root_job_id="draft-job-001",
        expected_requests={"ai-001": "ai", "knowledge-001": "knowledge"},
    )

    assert result.errors == ()
    assert result.envelope is not None
    assert result.envelope.responses[0].text == "local provider result"
    assert result.envelope.responses[1].items[0]["record_id"] == "rule-1"


def test_service_reader_rejects_wrong_identity_duplicate_and_unknown_ids(
    tmp_path: Path,
) -> None:
    response = {
        "request_id": "ai-001",
        "service": "ai",
        "status": "ok",
        "text": "result",
    }
    path = _write_envelope(
        tmp_path / "service-response.json",
        [response, response, {**response, "request_id": "unknown-001"}],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["task_id"] = "other-job-001"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = read_service_responses(
        path,
        root_job_id="draft-job-001",
        expected_requests={"ai-001": "ai"},
    )

    assert result.envelope is None
    assert {error.code for error in result.errors} == {
        "SERVICE_ROOT_JOB_MISMATCH",
        "SERVICE_RESPONSE_ID_DUPLICATE",
        "SERVICE_RESPONSE_ID_UNKNOWN",
    }


def test_invalid_envelope_returns_protocol_error_record(tmp_path: Path) -> None:
    invalid = tmp_path / "service-response.json"
    invalid.write_text("[]", encoding="utf-8")

    result = read_service_responses(
        invalid,
        root_job_id="draft-job-001",
        expected_requests={"ai-001": "ai"},
    )

    assert result.envelope is None
    assert result.errors[0].code == "SERVICE_ENVELOPE_INVALID"
    assert result.errors[0].field == "$"


def test_missing_service_file_returns_protocol_error_without_exception_details(
    tmp_path: Path,
) -> None:
    result = read_service_responses(
        tmp_path / "missing.json",
        root_job_id="draft-job-001",
        expected_requests={"ai-001": "ai"},
    )

    assert result.envelope is None
    assert result.errors[0].code == "PROTOCOL_FILE_MISSING"
    assert str(tmp_path) not in result.errors[0].message


def test_unexpected_service_file_is_ignored_when_no_requests_were_made(
    tmp_path: Path,
) -> None:
    unexpected = tmp_path / "untrusted.json"
    unexpected.write_text("{not-json", encoding="utf-8")

    result = read_service_responses(
        unexpected,
        root_job_id="draft-job-001",
        expected_requests={},
    )

    assert result.envelope is None
    assert result.errors == ()
