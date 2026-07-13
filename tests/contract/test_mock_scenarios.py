import json
import subprocess
import sys
from pathlib import Path

import pytest

from core.contracts.result import ModuleResult
from core.contracts.service_request import ServiceRequest


def write_job(tmp_path: Path, scenario: str, phase: str = "draft") -> tuple[Path, Path]:
    input_file = tmp_path / f"{scenario}.xlsx"
    input_file.write_bytes(b"mock")
    output_dir = tmp_path / f"out-{scenario}-{phase}"
    confirmation_file = None
    if phase == "finalize":
        confirmation_path = tmp_path / "confirmation.json"
        confirmation_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "job_id": "parent-1",
                    "answers": [
                        {
                            "confirmation_id": "mock-confirm-1",
                            "value": "人工值",
                            "apply_to_batch": False,
                            "remember_mapping": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        confirmation_file = str(confirmation_path.resolve())
    job = {
        "schema_version": "1.0",
        "job_id": f"job-{scenario}-{phase}",
        "module_id": "moisture",
        "phase": phase,
        "run_mode": "single",
        "input_files": [str(input_file.resolve())],
        "output_dir": str(output_dir.resolve()),
        "module_config_file": None,
        "ai_enabled": scenario == "ai",
        "allowed_knowledge_scopes": ["shared", "moisture"],
        "parent_job_id": "parent-1" if phase == "finalize" else None,
        "confirmation_file": confirmation_file,
        "service_response_file": None,
    }
    job_path = tmp_path / f"job-{scenario}-{phase}.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    return job_path, output_dir


def execute_job(job_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mock_modules.common.cli",
            "--module-id",
            "moisture",
            "run",
            "--job",
            str(job_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def run_mock(
    tmp_path: Path, scenario: str, phase: str = "draft"
) -> tuple[int, ModuleResult | None]:
    job_path, output_dir = write_job(tmp_path, scenario, phase)
    completed = execute_job(job_path)
    result_path = output_dir / "result.json"
    result = (
        ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        if result_path.exists() and scenario != "invalid"
        else None
    )
    return completed.returncode, result


def test_confirmation_finalizes_after_answer(tmp_path: Path) -> None:
    draft = run_mock(tmp_path, "confirm")[1]
    finalized = run_mock(tmp_path, "confirm", "finalize")[1]

    assert draft is not None
    assert draft.status.value == "needs_confirmation"
    assert len(draft.confirmations) == 1
    assert finalized is not None
    assert finalized.status.value == "success"
    assert finalized.confirmations == []
    assert finalized.summary.confirmation_count == 0


@pytest.mark.parametrize(
    "invalid_confirmation",
    ["missing", "malformed", "wrong-parent", "unrelated-answer"],
)
def test_confirmation_finalize_rejects_invalid_bundle_as_invalid_task(
    tmp_path: Path, invalid_confirmation: str
) -> None:
    job_path, output_dir = write_job(tmp_path, "confirm", "finalize")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    confirmation_path = Path(job["confirmation_file"])
    if invalid_confirmation == "missing":
        confirmation_path.unlink()
    elif invalid_confirmation == "malformed":
        confirmation_path.write_text("{invalid", encoding="utf-8")
    else:
        confirmation = json.loads(confirmation_path.read_text(encoding="utf-8"))
        if invalid_confirmation == "wrong-parent":
            confirmation["job_id"] = "different-parent"
        else:
            confirmation["answers"][0]["confirmation_id"] = "unrelated-confirmation"
        confirmation_path.write_text(json.dumps(confirmation), encoding="utf-8")

    completed = execute_job(job_path)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert completed.stderr.startswith("invalid confirmation bundle:")
    assert "traceback" not in completed.stderr.lower()
    assert not output_dir.exists()


def test_partial_scenario_reports_one_failed_input_and_keeps_outputs(tmp_path: Path) -> None:
    job_path, output_dir = write_job(tmp_path, "partial")
    later_input = tmp_path / "normal.xlsx"
    later_input.write_bytes(b"later mock")
    job = json.loads(job_path.read_text(encoding="utf-8"))
    job["input_files"].append(str(later_input.resolve()))
    job_path.write_text(json.dumps(job), encoding="utf-8")

    completed = execute_job(job_path)
    result = ModuleResult.model_validate_json(
        (output_dir / "result.json").read_text(encoding="utf-8")
    )

    assert completed.returncode == 0
    assert result.status.value == "partial_success"
    assert result.summary.input_count == 2
    assert result.summary.processed_count == 1
    assert result.summary.failed_count == 1
    assert result.errors == ["模拟单文件失败"]
    assert result.outputs
    assert len(result.file_results) == 2
    assert result.file_results[0].status.value == "failed"
    assert result.file_results[0].error == "模拟单文件失败"
    assert result.file_results[1].status.value == "success"
    assert result.file_results[1].error is None


def test_fail_scenario_reports_all_inputs_failed_without_outputs(tmp_path: Path) -> None:
    code, result = run_mock(tmp_path, "fail")

    assert code == 0
    assert result is not None
    assert result.status.value == "failed"
    assert result.summary.processed_count == 0
    assert result.summary.failed_count == 1
    assert result.errors == ["模拟任务失败"]
    assert result.outputs == []
    assert result.file_results[0].status.value == "failed"
    assert result.file_results[0].error == "模拟任务失败"


def test_invalid_scenario_writes_deliberately_malformed_result(tmp_path: Path) -> None:
    job_path, output_dir = write_job(tmp_path, "invalid")

    completed = execute_job(job_path)

    assert completed.returncode == 0
    assert (output_dir / "result.json").read_text(encoding="utf-8") == "{invalid"


def test_timeout_scenario_exceeds_short_caller_timeout(tmp_path: Path) -> None:
    job_path, output_dir = write_job(tmp_path, "timeout")

    with pytest.raises(subprocess.TimeoutExpired):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "mock_modules.common.cli",
                "--module-id",
                "moisture",
                "run",
                "--job",
                str(job_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )

    assert not (output_dir / "result.json").exists()


def test_crash_has_no_result(tmp_path: Path) -> None:
    code, result = run_mock(tmp_path, "crash")

    assert code == 3
    assert result is None


@pytest.mark.parametrize(
    ("scenario", "expected_request"),
    [
        (
            "ai",
            {
                "request_id": "ai-1",
                "service": "ai",
                "scope": None,
                "purpose": "生成模拟分析",
                "payload": {"metrics": [1, 2, 3]},
                "requires_user_consent": True,
            },
        ),
        (
            "knowledge",
            {
                "request_id": "kb-1",
                "service": "knowledge",
                "scope": "moisture",
                "purpose": "检索模拟规则",
                "payload": {"query": "异常处理"},
                "requires_user_consent": False,
            },
        ),
    ],
)
def test_service_scenarios_match_frozen_contract(
    tmp_path: Path, scenario: str, expected_request: dict[str, object]
) -> None:
    code, result = run_mock(tmp_path, scenario)

    assert code == 0
    assert result is not None
    expected = ServiceRequest.model_validate(expected_request)
    assert result.service_requests == [expected]
