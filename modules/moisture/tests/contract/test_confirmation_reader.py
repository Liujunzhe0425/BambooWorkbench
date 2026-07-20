# ruff: noqa: E402, I001

import json
import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.contract.confirmation_reader import read_confirmation_bundle


def _write_bundle(path: Path, **overrides: object) -> Path:
    payload: dict[str, object] = {
        "schema_version": "1.0",
        "job_id": "draft-job-001",
        "answers": [
            {
                "confirmation_id": "confirm-001",
                "value": "Sheet1",
                "apply_to_batch": False,
                "remember_mapping": False,
            }
        ],
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_confirmation_bundle_job_id_must_equal_root_job_id(tmp_path: Path) -> None:
    path = _write_bundle(tmp_path / "confirmation.json", job_id="other-job-001")

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids={"confirm-001"},
    )

    assert result.bundle is None
    assert result.errors[0].code == "CONFIRMATION_ROOT_JOB_MISMATCH"
    assert result.errors[0].field == "job_id"


def test_confirmation_reader_returns_immutable_dto(tmp_path: Path) -> None:
    path = _write_bundle(tmp_path / "confirmation.json")

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids={"confirm-001"},
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert result.bundle.job_id == "draft-job-001"
    assert result.bundle.answers[0].value == "Sheet1"
    try:
        result.bundle.job_id = "changed"  # type: ignore[misc]
    except (AttributeError, TypeError):
        pass
    else:  # pragma: no cover - documents the immutability contract
        raise AssertionError("confirmation DTO must be immutable")


def test_confirmation_reader_rejects_duplicate_and_unknown_ids(tmp_path: Path) -> None:
    duplicate = {
        "confirmation_id": "confirm-001",
        "value": "Sheet2",
        "apply_to_batch": False,
        "remember_mapping": False,
    }
    path = _write_bundle(
        tmp_path / "confirmation.json",
        answers=[duplicate, duplicate, {**duplicate, "confirmation_id": "unknown-001"}],
    )

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids={"confirm-001"},
    )

    assert result.bundle is None
    assert {error.code for error in result.errors} == {
        "CONFIRMATION_ID_DUPLICATE",
        "CONFIRMATION_ID_UNKNOWN",
    }


def test_confirmation_reader_can_ignore_framework_owned_service_consent(
    tmp_path: Path,
) -> None:
    module_answer = {
        "confirmation_id": "confirm-001",
        "value": "2026",
        "apply_to_batch": True,
        "remember_mapping": False,
    }
    service_answer = {
        "confirmation_id": "service-consent:ai-request-001",
        "value": "拒绝",
        "apply_to_batch": False,
        "remember_mapping": False,
    }
    path = _write_bundle(
        tmp_path / "confirmation.json",
        answers=[module_answer, service_answer],
    )

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids={"confirm-001"},
        ignored_confirmation_id_prefixes=("service-consent:",),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert [answer.confirmation_id for answer in result.bundle.answers] == ["confirm-001"]


def test_confirmation_reader_returns_protocol_errors_for_invalid_or_missing_file(
    tmp_path: Path,
) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{not-json", encoding="utf-8")

    malformed = read_confirmation_bundle(
        invalid,
        root_job_id="draft-job-001",
        expected_confirmation_ids=set(),
    )
    missing = read_confirmation_bundle(
        tmp_path / "missing.json",
        root_job_id="draft-job-001",
        expected_confirmation_ids=set(),
    )

    assert malformed.errors[0].code == "PROTOCOL_JSON_INVALID"
    assert missing.errors[0].code == "PROTOCOL_FILE_MISSING"
    assert "JSONDecodeError" not in malformed.errors[0].message
    assert str(tmp_path) not in missing.errors[0].message


def test_empty_confirmation_bundle_is_valid_when_no_answers_are_expected(
    tmp_path: Path,
) -> None:
    path = _write_bundle(tmp_path / "confirmation.json", answers=[])

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids=set(),
    )

    assert result.errors == ()
    assert result.bundle is not None
    assert result.bundle.answers == ()


def test_confirmation_reader_rejects_each_missing_expected_answer(
    tmp_path: Path,
) -> None:
    present = {
        "confirmation_id": "confirm-present",
        "value": "Sheet1",
        "apply_to_batch": False,
        "remember_mapping": False,
    }
    path = _write_bundle(tmp_path / "confirmation.json", answers=[present])

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids={
            "confirm-missing-z",
            "confirm-present",
            "confirm-missing-a",
        },
    )

    assert result.bundle is None
    assert [
        (error.code, error.field, error.message) for error in result.errors
    ] == [
        (
            "CONFIRMATION_ID_MISSING",
            "answers.confirm-missing-a",
            "expected confirmation answer is missing",
        ),
        (
            "CONFIRMATION_ID_MISSING",
            "answers.confirm-missing-z",
            "expected confirmation answer is missing",
        ),
    ]


def test_confirmation_reader_rejects_empty_answers_when_one_is_expected(
    tmp_path: Path,
) -> None:
    path = _write_bundle(tmp_path / "confirmation.json", answers=[])

    result = read_confirmation_bundle(
        path,
        root_job_id="draft-job-001",
        expected_confirmation_ids={"confirm-001"},
    )

    assert result.bundle is None
    assert [(error.code, error.field) for error in result.errors] == [
        ("CONFIRMATION_ID_MISSING", "answers.confirm-001")
    ]
