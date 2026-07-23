import pytest
from pydantic import ValidationError

from core.contracts.management import (
    ApprovedExperienceItem,
    HistorySummaryItem,
    ModuleManagementOperation,
    ModuleManagementRequest,
    ModuleManagementResponse,
)


def test_management_request_requires_operation_specific_fields() -> None:
    request = ModuleManagementRequest(
        schema_version="1.0",
        request_id="request-1",
        module_id="moisture",
        operation="import_history_summary",
        data_dir=r"D:\BambooWorkbench\module-data\moisture",
        input_file=r"D:\input\history.xlsx",
    )
    assert request.operation is ModuleManagementOperation.IMPORT_HISTORY_SUMMARY

    with pytest.raises(ValidationError):
        ModuleManagementRequest(
            schema_version="1.0",
            request_id="request-2",
            module_id="moisture",
            operation="import_history_summary",
            data_dir=r"D:\data",
        )


def test_management_response_rejects_paths_in_public_labels() -> None:
    with pytest.raises(ValidationError):
        HistorySummaryItem(
            history_id="history-1",
            display_name=r"D:\private\history.xlsx",
            sha256="a" * 64,
        )
    with pytest.raises(ValidationError):
        ApprovedExperienceItem(
            entry_id="experience-1",
            title="unsafe\ntrace",
            version="1.0.0",
            sha256="b" * 64,
        )


def test_management_response_enforces_identity_payload_shape() -> None:
    response = ModuleManagementResponse(
        schema_version="1.0",
        request_id="request-3",
        module_id="moisture",
        operation="list_history_summaries",
        status="ok",
        history_items=[
            {
                "history_id": "history-1",
                "display_name": "2026年4月汇总",
                "sha256": "c" * 64,
            }
        ],
    )
    assert response.history_items[0].display_name == "2026年4月汇总"

    with pytest.raises(ValidationError):
        ModuleManagementResponse(
            schema_version="1.0",
            request_id="request-4",
            module_id="moisture",
            operation="list_history_summaries",
            status="error",
            error_code="FAILED",
            message="失败",
            history_items=[
                {
                    "history_id": "history-1",
                    "display_name": "不应出现",
                    "sha256": "d" * 64,
                }
            ],
        )
