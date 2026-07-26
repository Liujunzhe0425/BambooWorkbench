from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt

from core.contracts.result import ConfirmationPrompt, SourceRef
from core.security.credentials import InMemoryCredentialStore
from ui.pages.confirmations_page import ConfirmationsPage
from ui.pages.monthly_history_page import MonthlyHistoryPage
from ui.pages.pending_list_page import PendingListPage
from ui.pages.settings_page import SettingsPage


def test_monthly_history_defaults_to_twelve_disabled_cards_without_extra_text(
    qtbot, app_context
) -> None:
    page = MonthlyHistoryPage(app_context.monthly_repository)
    qtbot.addWidget(page)

    assert len(page.cards) == 12
    assert all(not card.isEnabled() for card in page.cards)
    assert all("不可点击" not in card.text() for card in page.cards)
    assert page.module_buttons["moisture"].isChecked()


def test_pending_list_only_shows_waiting_tasks_newest_first(qtbot, app_context) -> None:
    repository = app_context.task_repository
    confirmations = app_context.confirmation_repository
    prompt = ConfirmationPrompt(
        confirmation_id="confirmation-1",
        field="字段",
        reason="原因",
        suggested_value="A",
        options=["A", "B"],
        confidence=0.5,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file="D:/source.xlsx"),
    )
    for index, status in enumerate(("waiting_confirmation", "success"), 1):
        job_id = f"job-list-{index:03d}"
        repository.create(
            job_id,
            "moisture",
            status,
            datetime(2026, 7, index, tzinfo=UTC).isoformat(),
            task_name=f"任务{index}",
            period_year=2026,
            period_month=index,
        )
        if status == "waiting_confirmation":
            confirmations.save_prompts(job_id, [prompt])
    page = PendingListPage(repository)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 1
    assert page.table.item(0, 0).text() == "任务1"
    assert page.table.item(0, 5).text() == "1"


def test_confirmation_page_emits_local_draft_after_each_answer_change(
    qtbot, tmp_path: Path
) -> None:
    page = ConfirmationsPage()
    qtbot.addWidget(page)
    prompt = ConfirmationPrompt(
        confirmation_id="confirmation-draft-1",
        field="字段",
        reason="原因",
        suggested_value="A",
        options=["A", "B"],
        confidence=0.5,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file=str(tmp_path / "source.xlsx")),
    )
    page.load("job-draft-001", [prompt])

    with qtbot.waitSignal(page.draft_changed) as signal:
        page.answer_inputs[prompt.confirmation_id].setCurrentText("B")

    assert signal.args[0] == "job-draft-001"
    assert signal.args[1][0].value == "B"
    assert signal.args[2] is True


def test_settings_deletes_ai_and_update_credentials_independently(
    qtbot, app_context
) -> None:
    credentials = InMemoryCredentialStore()
    credentials.set_secret("deepseek", "ai-secret")
    credentials.set_secret("github-updates", "update-secret")
    app_context.settings.set("ai_provider", "deepseek")
    page = SettingsPage(
        app_context.settings,
        app_context.paths,
        credentials,
        app_context.credential_state_repository,
        app_context.output_root_repository,
    )
    qtbot.addWidget(page)

    qtbot.mouseClick(page.delete_ai_key_button, Qt.MouseButton.LeftButton)
    assert not credentials.has_secret("deepseek")
    assert credentials.has_secret("github-updates")

    qtbot.mouseClick(page.delete_update_token_button, Qt.MouseButton.LeftButton)
    assert not credentials.has_secret("github-updates")
