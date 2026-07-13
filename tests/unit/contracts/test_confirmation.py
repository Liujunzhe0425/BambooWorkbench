import pytest
from pydantic import ValidationError

from core.contracts.confirmation import ConfirmationBundle


def test_confirmation_bundle_rejects_unsupported_schema_version() -> None:
    with pytest.raises(ValidationError):
        ConfirmationBundle.model_validate(
            {
                "schema_version": "2.0",
                "job_id": "parent-1",
                "answers": [],
            }
        )
