import pytest

from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository


def _record(
    record_id: str,
    namespace: str,
    title: str,
    source_kind: KnowledgeSourceKind,
    *,
    enabled: bool = True,
) -> KnowledgeRecord:
    return KnowledgeRecord(
        record_id,
        namespace,
        title,
        f"{title}内容",
        source_kind,
        enabled,
    )


def test_confirmed_rules_rank_before_examples_and_shared_is_inherited(database) -> None:
    repository = KnowledgeRepository(database)
    repository.add(
        _record(
            "example-1",
            "moisture",
            "水分历史案例",
            KnowledgeSourceKind.HISTORICAL_EXAMPLE,
        )
    )
    repository.add(
        _record(
            "rule-1",
            "shared",
            "水分正式规则",
            KnowledgeSourceKind.CONFIRMED_RULE,
        )
    )

    results = repository.search("moisture", "水分")

    assert [item.record_id for item in results] == ["rule-1", "example-1"]


def test_disabled_records_are_hidden_and_namespaces_are_validated(database) -> None:
    repository = KnowledgeRepository(database)
    repository.add(
        _record(
            "rule-1",
            "shared",
            "水分规则",
            KnowledgeSourceKind.CONFIRMED_RULE,
        )
    )
    repository.set_enabled("rule-1", False)

    assert repository.search("shared", "水分") == []
    with pytest.raises(ValueError, match="namespace"):
        repository.search("unauthorized", "水分")
