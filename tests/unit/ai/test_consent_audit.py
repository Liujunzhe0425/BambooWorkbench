from core.ai.audit import ConsentAuditRepository, ConsentDecision


def test_records_decision_without_request_body(database) -> None:
    repository = ConsentAuditRepository(database)
    repository.record(
        ConsentDecision(
            task_id="task-1",
            module_id="after_sales",
            provider_id="mock",
            allowed=False,
            data_categories=("local_path",),
            decided_at="2026-07-13T09:00:00+08:00",
        )
    )

    row = repository.list_for_task("task-1")[0]
    assert row.allowed is False
    assert row.data_categories == ("local_path",)
    assert not hasattr(row, "request_body")
    assert database.scalar(
        "SELECT COUNT(*) FROM pragma_table_info('ai_consent_audit') "
        "WHERE name IN ('request_body', 'api_key')"
    ) == 0
