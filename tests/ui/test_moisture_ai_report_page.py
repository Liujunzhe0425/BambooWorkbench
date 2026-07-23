from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from ui.pages.moisture_ai_report_page import MoistureAIReportPage


class FakeManagement(QObject):
    progress = Signal(object, object)
    completed = Signal(object, object)
    failed = Signal(object, str)
    cancelled = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.is_running = False

    def is_available(self, module_id: ModuleId) -> bool:
        return module_id is ModuleId.MOISTURE

    def cancel(self) -> bool:
        return False


def test_ai_report_page_emits_canonical_current_only_config(qtbot, tmp_path: Path) -> None:
    page = MoistureAIReportPage(FakeManagement())
    qtbot.addWidget(page)
    summary = tmp_path / "水分汇总.xlsx"
    summary.write_bytes(b"xlsx")
    page.current_summary = summary.resolve()
    page.current_label.setText(summary.name)
    page.question_edit.setPlainText("请列出需要人工复核的批次")
    requested = QSignalSpy(page.task_requested)

    page._prepare()

    assert requested.count() == 1
    assert requested.at(0)[0] == summary.resolve()
    assert requested.at(0)[1] == {
        "schema_version": "1.0",
        "operation": "ai_report",
        "inputs": [{"role": "current_summary", "input_index": 0}],
        "history_ids": [],
        "experience_selections": [],
        "question": "请列出需要人工复核的批次",
    }
