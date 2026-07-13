from dataclasses import dataclass
from enum import StrEnum

ALLOWED_NAMESPACES = frozenset({"shared", "moisture", "boiling", "after_sales"})


class KnowledgeSourceKind(StrEnum):
    CONFIRMED_RULE = "confirmed_rule"
    CURRENT_CONFIRMATION = "current_confirmation"
    HISTORICAL_EXAMPLE = "historical_example"
    MODEL_KNOWLEDGE = "model_knowledge"


SOURCE_PRIORITY = {
    KnowledgeSourceKind.CONFIRMED_RULE: 0,
    KnowledgeSourceKind.CURRENT_CONFIRMATION: 1,
    KnowledgeSourceKind.HISTORICAL_EXAMPLE: 2,
    KnowledgeSourceKind.MODEL_KNOWLEDGE: 3,
}


@dataclass(frozen=True)
class KnowledgeRecord:
    record_id: str
    namespace: str
    title: str
    content: str
    source_kind: KnowledgeSourceKind
    enabled: bool
    source_path: str | None = None

    def __post_init__(self) -> None:
        if self.namespace not in ALLOWED_NAMESPACES:
            raise ValueError(f"unsupported knowledge namespace: {self.namespace}")
        if not self.record_id or not self.title:
            raise ValueError("knowledge record ID and title are required")
