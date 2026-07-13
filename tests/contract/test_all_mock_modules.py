from pathlib import Path

import pytest

from core.contracts.validator import validate_module


@pytest.mark.parametrize("module_id", ["moisture", "boiling", "after_sales"])
def test_mock_module_package_is_valid(module_id: str) -> None:
    module_dir = Path("mock_modules") / module_id
    report = validate_module(module_dir)
    assert report.ok, [issue.message for issue in report.issues]
