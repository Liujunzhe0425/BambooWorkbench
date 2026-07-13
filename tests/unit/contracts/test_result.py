import pytest
from pydantic import ValidationError

from core.contracts.progress import ProgressEvent
from core.contracts.result import ModuleResult


def test_progress_percent_is_bounded() -> None:
    assert ProgressEvent(type="progress", percent=40, message="处理中").percent == 40
    with pytest.raises(ValidationError):
        ProgressEvent(type="progress", percent=101, message="invalid")


def test_confirmation_result_requires_prompts() -> None:
    with pytest.raises(ValidationError):
        ModuleResult.model_validate(
            {
                "schema_version": "1.0",
                "job_id": "20260713-0001",
                "module_id": "moisture",
                "module_version": "0.1.0",
                "status": "needs_confirmation",
                "summary": {
                    "input_count": 1,
                    "processed_count": 1,
                    "skipped_count": 0,
                    "failed_count": 0,
                    "anomaly_count": 0,
                    "confirmation_count": 0,
                },
                "confirmations": [],
                "started_at": "2026-07-13T09:00:00+08:00",
                "finished_at": "2026-07-13T09:00:01+08:00",
            }
        )
