import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.result import ConfirmationPrompt, OutputArtifact, SourceRef
from core.platform.paths import AppPaths
from core.storage.database import Database
from core.storage.repositories.confirmations import ConfirmationRepository
from core.storage.repositories.modules import ModuleRepository
from core.storage.repositories.tasks import TaskRepository


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    opened = Database.open(AppPaths.for_root(tmp_path))
    opened.migrate()
    try:
        yield opened
    finally:
        opened.close()


def test_task_repository_records_lifecycle(database: Database) -> None:
    repository = TaskRepository(database)
    repository.create("job-001", "moisture", "created", "2026-07-13T10:00:00+08:00")

    repository.update_status(
        "job-001",
        "running_draft",
        error="先前错误",
        result_path="D:/结果/result.json",
    )

    record = repository.get("job-001")
    assert record["module_id"] == "moisture"
    assert record["status"] == "running_draft"
    assert record["updated_at"] != record["created_at"]
    assert record["error"] == "先前错误"
    assert record["result_path"] == "D:/结果/result.json"
    assert repository.list_recent() == [{"task_number": 1, **record}]
    assert repository.get_number("job-001") == 1
    with pytest.raises(KeyError):
        repository.get("missing")
    with pytest.raises(KeyError):
        repository.get_number("missing")


def test_task_numbers_are_base_one_and_stable_in_recent_order(database: Database) -> None:
    repository = TaskRepository(database)
    repository.create("job-late", "boiling", "success", "2026-07-13T11:00:00+08:00")
    repository.create("job-early", "moisture", "success", "2026-07-13T10:00:00+08:00")
    repository.create("job-latest", "after_sales", "success", "2026-07-13T12:00:00+08:00")

    records = repository.list_recent()

    assert [(item["job_id"], item["task_number"]) for item in records] == [
        ("job-latest", 3),
        ("job-late", 2),
        ("job-early", 1),
    ]
    assert repository.get_number("job-early") == 1


def test_task_repository_records_files_and_replaces_outputs(database: Database) -> None:
    repository = TaskRepository(database)
    repository.create("job-001", "moisture", "created", "2026-07-13T10:00:00+08:00")
    repository.add_file(
        "job-001", "D:/源/样品.xlsx", "D:/快照/样品.xlsx", "abc123", "snapshotted"
    )
    first = OutputArtifact(
        type="workbook",
        path="D:/输出/初稿.xlsx",
        label="初稿",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    final = first.model_copy(update={"path": "D:/输出/终稿.xlsx", "label": "终稿"})

    repository.replace_outputs("job-001", [first])
    repository.replace_outputs("job-001", [final])

    assert repository.list_files("job-001") == [
        {
            "job_id": "job-001",
            "source_path": "D:/源/样品.xlsx",
            "snapshot_path": "D:/快照/样品.xlsx",
            "fingerprint": "abc123",
            "status": "snapshotted",
        }
    ]
    assert repository.list_outputs("job-001") == [
        {
            "job_id": "job-001",
            "artifact_type": "workbook",
            "path": "D:/输出/终稿.xlsx",
            "label": "终稿",
        }
    ]


def test_task_repository_add_files_rolls_back_the_whole_batch(database: Database) -> None:
    repository = TaskRepository(database)
    repository.create("job-001", "moisture", "created", "2026-07-13T10:00:00+08:00")
    duplicate_source_rows = [
        ("source.xlsx", "snapshot-1.xlsx", "fingerprint-1", "snapshotted"),
        ("source.xlsx", "snapshot-2.xlsx", "fingerprint-2", "snapshotted"),
    ]

    with pytest.raises(sqlite3.IntegrityError):
        repository.add_files("job-001", duplicate_source_rows)

    assert repository.list_files("job-001") == []


def test_task_owned_rows_enforce_foreign_keys_and_cascade(database: Database) -> None:
    repository = TaskRepository(database)

    with pytest.raises(sqlite3.IntegrityError):
        repository.add_file("missing", "source", "snapshot", "fingerprint", "created")

    repository.create("job-001", "moisture", "created", "2026-07-13T10:00:00+08:00")
    repository.add_file("job-001", "source", "snapshot", "fingerprint", "created")
    repository.replace_outputs(
        "job-001",
        [
            OutputArtifact(
                type="json",
                path="result.json",
                label="result",
                mime_type="application/json",
            )
        ],
    )
    database.execute("DELETE FROM tasks WHERE job_id = ?", ("job-001",))

    assert database.scalar("SELECT COUNT(*) FROM task_files") == 0
    assert database.scalar("SELECT COUNT(*) FROM outputs") == 0


def test_module_repository_upserts_and_lists_modules(database: Database) -> None:
    repository = ModuleRepository(database)
    repository.upsert("moisture", "1.0.0", "D:/模块/水分", True, "healthy")
    repository.upsert("moisture", "1.1.0", "D:/模块/水分", False, "degraded")

    assert repository.list_all() == [
        {
            "module_id": "moisture",
            "version": "1.1.0",
            "path": "D:/模块/水分",
            "is_mock": False,
            "health": "degraded",
        }
    ]


def test_confirmation_repository_round_trips_full_typed_json(database: Database) -> None:
    TaskRepository(database).create(
        "job-001", "moisture", "created", "2026-07-13T10:00:00+08:00"
    )
    repository = ConfirmationRepository(database)
    prompt = ConfirmationPrompt(
        confirmation_id="confirm-001",
        field="批次",
        reason="需要人工确认",
        suggested_value={"候选": "甲"},
        options=["甲", {"值": "乙"}],
        confidence=0.75,
        blocking=True,
        batch_applicable=True,
        rememberable=False,
        source=SourceRef(source_file="样品.xlsx", sheet="数据", cell_or_range="A2"),
    )
    answer = ConfirmationAnswer(
        confirmation_id="confirm-001",
        value={"选择": "乙"},
        apply_to_batch=True,
    )

    repository.save_prompts("job-001", [prompt])
    repository.save_answers("job-001", [answer])

    stored = repository.list_for_job("job-001")
    assert stored[0]["original_prompt"] == prompt.model_dump(mode="json")
    assert stored[0]["answer"] == answer.model_dump(mode="json")
    assert stored[0]["answered_at"] is not None
    raw = database.connection.execute(
        "SELECT original_prompt, answer FROM confirmations WHERE job_id = ?",
        ("job-001",),
    ).fetchone()
    assert raw is not None
    assert json.loads(raw["original_prompt"])["reason"] == "需要人工确认"
    assert "需要人工确认" in raw["original_prompt"]
    assert "选择" in raw["answer"]


def test_unknown_confirmation_answer_raises_without_implicit_or_partial_rows(
    database: Database,
) -> None:
    TaskRepository(database).create(
        "job-001", "moisture", "created", "2026-07-13T10:00:00+08:00"
    )
    repository = ConfirmationRepository(database)
    prompt = ConfirmationPrompt(
        confirmation_id="known",
        field="field",
        reason="reason",
        confidence=1,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file="sample.xlsx"),
    )
    repository.save_prompts("job-001", [prompt])
    known = ConfirmationAnswer(confirmation_id="known", value="valid")
    unknown = ConfirmationAnswer(confirmation_id="unknown", value="invalid")

    with pytest.raises(KeyError, match="unknown"):
        repository.save_answers("job-001", [known, unknown])

    assert repository.list_for_job("job-001")[0]["answer"] is None
    assert database.scalar(
        "SELECT COUNT(*) FROM confirmations WHERE confirmation_id = ?", ("unknown",)
    ) == 0


def test_confirmation_repository_replace_answers_clears_omitted_optional_answer(
    database: Database,
) -> None:
    TaskRepository(database).create(
        "job-001", "moisture", "created", "2026-07-13T10:00:00+08:00"
    )
    repository = ConfirmationRepository(database)
    prompts = [
        ConfirmationPrompt(
            confirmation_id=confirmation_id,
            field=confirmation_id,
            reason="reason",
            confidence=1,
            blocking=blocking,
            batch_applicable=True,
            rememberable=True,
            source=SourceRef(source_file="sample.xlsx"),
        )
        for confirmation_id, blocking in (("blocking", True), ("optional", False))
    ]
    blocking = ConfirmationAnswer(confirmation_id="blocking", value="required")
    optional = ConfirmationAnswer(
        confirmation_id="optional",
        value={"choice": "optional"},
        apply_to_batch=True,
        remember_mapping=True,
    )
    repository.save_prompts("job-001", prompts)

    repository.replace_answers("job-001", [blocking, optional])
    repository.replace_answers("job-001", [blocking])

    stored = repository.list_for_job("job-001")
    assert stored[0]["answer"] == blocking.model_dump(mode="json")
    assert stored[0]["answered_at"] is not None
    assert stored[1]["answer"] is None
    assert stored[1]["answered_at"] is None


@pytest.mark.parametrize("invalid_kind", ["unknown", "duplicate"])
def test_confirmation_repository_replace_answers_rejects_before_clearing_existing_answers(
    database: Database, invalid_kind: str
) -> None:
    TaskRepository(database).create(
        "job-001", "moisture", "created", "2026-07-13T10:00:00+08:00"
    )
    repository = ConfirmationRepository(database)
    prompt = ConfirmationPrompt(
        confirmation_id="known",
        field="field",
        reason="reason",
        confidence=1,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file="sample.xlsx"),
    )
    existing = ConfirmationAnswer(confirmation_id="known", value="existing")
    repository.save_prompts("job-001", [prompt])
    repository.save_answers("job-001", [existing])
    invalid = (
        [ConfirmationAnswer(confirmation_id="unknown", value="invalid")]
        if invalid_kind == "unknown"
        else [existing, existing]
    )

    with pytest.raises((KeyError, ValueError), match=invalid_kind):
        repository.replace_answers("job-001", invalid)

    assert repository.list_for_job("job-001")[0]["answer"] == existing.model_dump(
        mode="json"
    )
