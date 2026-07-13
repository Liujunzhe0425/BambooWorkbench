from core.security.redaction import RedactionService


def test_redacts_paths_sensitive_fields_and_nested_personal_values() -> None:
    source = {
        "operator_name": "张三",
        "file": r"D:\客户资料\售后.xlsx",
        "summary": "批次 B-2026-01 需要复核",
        "contacts": [{"value": "13800138000"}, {"value": "quality@example.com"}],
    }

    result = RedactionService().redact(source)

    assert result.payload["operator_name"] == "[REDACTED]"
    assert result.payload["file"] == "[LOCAL_PATH]"
    assert result.payload["summary"] == "批次 B-2026-01 需要复核"
    assert result.payload["contacts"] == [
        {"value": "[REDACTED]"},
        {"value": "[REDACTED]"},
    ]
    assert set(result.categories) == {
        "local_path",
        "personal_field",
        "personal_value",
    }


def test_redaction_does_not_mutate_source() -> None:
    source = {"file": r"D:\input.xlsx"}
    RedactionService().redact(source)
    assert source["file"] == r"D:\input.xlsx"
