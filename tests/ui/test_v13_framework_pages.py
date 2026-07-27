from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt

from core.contracts.enums import ModuleId
from core.contracts.result import ConfirmationPrompt, SourceRef
from core.security.credentials import InMemoryCredentialStore
from ui.main_window import MainWindow
from ui.page_ids import PageId
from ui.pages.confirmations_page import ConfirmationsPage
from ui.pages.knowledge_page import KnowledgePage
from ui.pages.module_task_page import ModuleTaskPage
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


class _MonthlyHistoryRepository:
    def list_year(self, _module_id: str, _year: int) -> list[dict[str, object]]:
        return [
            {
                "month": 3,
                "official_job_id": "job-history-003",
                "result_integrity": "ok",
            }
        ]

    def active_months(self, _module_id: str, _year: int) -> set[int]:
        return set()


def test_monthly_history_fills_responsive_grid_and_exposes_selected_module(
    qtbot,
) -> None:
    page = MonthlyHistoryPage(_MonthlyHistoryRepository())
    qtbot.addWidget(page)
    page.resize(970, 720)
    page.show()
    qtbot.waitUntil(lambda: page._columns == 4)

    assert page.year_combo.itemData(0) == 2077
    assert page.year_combo.findData(2000) >= 0
    assert all(card.height() >= 104 for card in page.cards)
    assert abs(page.grid_host.width() - page.cards[3].geometry().right()) <= 1
    assert page.cards[2].isEnabled()

    qtbot.mouseClick(page.module_buttons["boiling"], Qt.MouseButton.LeftButton)
    assert page.module_id == "boiling"
    assert page.module_buttons["boiling"].isChecked()
    assert not page.module_buttons["moisture"].isChecked()
    assert page.module_buttons["boiling"].property("historyModule") is True

    page.resize(760, 720)
    qtbot.waitUntil(
        lambda: page._columns == 3
        and abs(page.grid_host.width() - page.cards[2].geometry().right()) <= 1
    )


def test_monthly_history_created_card_opens_complete_result(qtbot) -> None:
    page = MonthlyHistoryPage(_MonthlyHistoryRepository())
    qtbot.addWidget(page)

    with qtbot.waitSignal(page.result_requested) as signal:
        qtbot.mouseClick(page.cards[2], Qt.MouseButton.LeftButton)

    assert signal.args == ["job-history-003"]


def test_task_and_knowledge_pages_scroll_without_compressing_controls(
    qtbot, tmp_path: Path
) -> None:
    task_page = ModuleTaskPage(tmp_path / "source")
    task_page.set_module(
        ModuleId.MOISTURE,
        "竹丝水分检测",
        [".xlsx"],
        ai_report_available=True,
        governance_available=True,
    )
    qtbot.addWidget(task_page)
    task_page.resize(760, 480)
    task_page.show()

    knowledge_page = KnowledgePage()
    qtbot.addWidget(knowledge_page)
    knowledge_page.resize(760, 480)
    knowledge_page.show()
    qtbot.waitUntil(
        lambda: task_page.scroll_area.verticalScrollBar().maximum() > 0
        and knowledge_page.scroll_area.verticalScrollBar().maximum() > 0
    )

    assert task_page.scroll_area.horizontalScrollBar().maximum() == 0
    assert knowledge_page.scroll_area.horizontalScrollBar().maximum() == 0
    for control in (
        task_page.year_spin,
        task_page.month_combo,
        task_page.task_name_edit,
        task_page.operation_combo,
        knowledge_page.namespace_combo,
        knowledge_page.query_edit,
        knowledge_page.search_button,
    ):
        assert control.height() >= control.minimumSizeHint().height()


def test_minimum_main_window_keeps_task_and_knowledge_controls_readable(
    qtbot, app_context
) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.resize(980, 660)
    window.show()

    window.workbench_page.module_selected.emit(ModuleId.MOISTURE)
    qtbot.waitUntil(lambda: window.stack.currentWidget() is window.module_task_page)
    assert (
        window.module_task_page.task_name_edit.height()
        >= window.module_task_page.task_name_edit.minimumSizeHint().height()
    )
    assert window.module_task_page.scroll_area.horizontalScrollBar().maximum() == 0

    window.navigate(PageId.KNOWLEDGE)
    qtbot.waitUntil(
        lambda: window.stack.currentWidget() is window.knowledge_page
        and window.knowledge_page.scroll_area.verticalScrollBar().maximum() > 0
    )
    assert (
        window.knowledge_page.query_edit.height()
        >= window.knowledge_page.query_edit.minimumSizeHint().height()
    )


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
