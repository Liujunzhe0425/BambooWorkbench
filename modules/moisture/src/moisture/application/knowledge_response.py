"""Validate Knowledge responses as non-decision report citations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from moisture.contract.service_response_reader import ServiceResponse
from moisture.ports.writers import KnowledgeCitation

_FIELDS = {"record_id", "namespace", "title", "content", "source_kind", "source_path"}
_MAX_TEXT = 4_000


class KnowledgeResponseValidationError(ValueError):
    """Knowledge response cannot be safely cited."""


def validate_knowledge_citations(
    responses: Iterable[ServiceResponse],
    *,
    allowed_scopes: set[str],
) -> tuple[KnowledgeCitation, ...]:
    citations: list[KnowledgeCitation] = []
    seen: set[tuple[str, str]] = set()
    for response in responses:
        if response.service != "knowledge":
            continue
        if response.status != "ok":
            raise KnowledgeResponseValidationError("knowledge service did not return ok")
        for item in response.items:
            citations.append(_citation(item, allowed_scopes, seen))
    return tuple(sorted(citations, key=lambda item: (item.namespace, item.record_id)))


def _citation(
    item: Mapping[str, object],
    allowed_scopes: set[str],
    seen: set[tuple[str, str]],
) -> KnowledgeCitation:
    if set(item) != _FIELDS:
        raise KnowledgeResponseValidationError("knowledge item fields are invalid")
    required = ("record_id", "namespace", "title", "content", "source_kind")
    if any(not isinstance(item.get(field), str) for field in required):
        raise KnowledgeResponseValidationError("knowledge item text fields are invalid")
    values = {field: str(item[field]).strip() for field in required}
    if any(not value or len(value) > _MAX_TEXT for value in values.values()):
        raise KnowledgeResponseValidationError("knowledge item text is blank or oversized")
    namespace = values["namespace"]
    if namespace not in allowed_scopes or namespace not in {"moisture", "shared"}:
        raise KnowledgeResponseValidationError("knowledge namespace is not authorized")
    identity = (namespace, values["record_id"])
    if identity in seen:
        raise KnowledgeResponseValidationError("knowledge item identity is duplicated")
    seen.add(identity)
    raw_source = item.get("source_path")
    if raw_source is not None and not isinstance(raw_source, str):
        raise KnowledgeResponseValidationError("knowledge source path is invalid")
    source_name = Path(raw_source).name if isinstance(raw_source, str) and raw_source else None
    source = values["source_kind"]
    if source_name:
        source = f"{source}:{source_name}"
    return KnowledgeCitation(
        record_id=values["record_id"],
        namespace=namespace,
        title=values["title"],
        content=values["content"],
        source=source,
    )
