import pytest
from pydantic import ValidationError

from core.contracts.job import JobRequest


def test_draft_job_requires_absolute_inputs() -> None:
    job = JobRequest.model_validate(
        {
            "schema_version": "1.0",
            "job_id": "20260713-0001",
            "module_id": "moisture",
            "phase": "draft",
            "run_mode": "batch",
            "input_files": ["D:/data/example.xlsx"],
            "output_dir": "D:/output/20260713-0001",
            "module_config_file": None,
            "ai_enabled": False,
            "allowed_knowledge_scopes": ["shared", "moisture"],
        }
    )
    assert job.phase.value == "draft"
    assert job.confirmation_file is None


def test_finalize_job_requires_confirmation_file() -> None:
    with pytest.raises(ValidationError):
        JobRequest.model_validate(
            {
                "schema_version": "1.0",
                "job_id": "20260713-0002",
                "module_id": "moisture",
                "phase": "finalize",
                "run_mode": "batch",
                "input_files": ["D:/data/example.xlsx"],
                "output_dir": "D:/output/20260713-0002",
                "parent_job_id": "20260713-0001",
                "ai_enabled": False,
                "allowed_knowledge_scopes": ["shared", "moisture"],
            }
        )
