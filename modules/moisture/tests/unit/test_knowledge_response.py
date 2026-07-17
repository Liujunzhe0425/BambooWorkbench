from __future__ import annotations

import pytest
from moisture.application.knowledge_response import (
    KnowledgeResponseValidationError,
    validate_knowledge_citations,
)
from moisture.contract.service_response_reader import ServiceResponse


def _response(*, status: str = "ok", namespace: str = "moisture") -> ServiceResponse:
    return ServiceResponse(
        request_id="knowledge-1",
        service="knowledge",
        status=status,
        items=(
            {
                "record_id": "EXP-001",
                "namespace": namespace,
                "title": "复核指引",
                "content": "仅作报告引用，不改变颜色。",
                "source_kind": "local_document",
                "source_path": r"C:\private\guidance.md",
            },
        ),
    )


def test_valid_knowledge_response_becomes_sanitized_report_citation() -> None:
    citations = validate_knowledge_citations(
        (_response(),), allowed_scopes={"moisture", "shared"}
    )

    assert citations[0].record_id == "EXP-001"
    assert citations[0].source == "local_document:guidance.md"
    assert "C:\\private" not in citations[0].source


@pytest.mark.parametrize(
    "response, scopes",
    [
        (_response(status="denied"), {"moisture"}),
        (_response(namespace="private"), {"moisture", "private"}),
        (_response(namespace="shared"), {"moisture"}),
    ],
)
def test_non_ok_or_unauthorized_knowledge_is_rejected(response, scopes) -> None:
    with pytest.raises(KnowledgeResponseValidationError):
        validate_knowledge_citations((response,), allowed_scopes=scopes)


def test_duplicate_knowledge_identity_is_rejected() -> None:
    with pytest.raises(KnowledgeResponseValidationError, match="duplicated"):
        validate_knowledge_citations(
            (_response(), _response()), allowed_scopes={"moisture"}
        )
