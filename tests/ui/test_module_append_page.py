from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QSignalSpy

from core.contracts.enums import ModuleId
from ui.pages.module_task_page import ModuleTaskPage


def test_moisture_incremental_entry_builds_exact_input_roles(qtbot, tmp_path: Path) -> None:
    base = tmp_path / "history.xlsx"
    raw_one = tmp_path / "new-one.xlsx"
    raw_two = tmp_path / "new-two.xlsx"
    for path in (base, raw_one, raw_two):
        path.write_bytes(b"xlsx")
    page = ModuleTaskPage()
    qtbot.addWidget(page)
    page.set_module(
        ModuleId.MOISTURE,
        "竹丝水分检测",
        [".xlsx"],
        incremental_available=True,
    )
    page.operation_combo.setCurrentIndex(1)
    page.base_summary = base.resolve()
    page.base_summary_edit.setText(str(base.resolve()))
    page.add_files([raw_one, raw_two])
    requested = QSignalSpy(page.configured_task_requested)

    qtbot.mouseClick(page.run_button, Qt.MouseButton.LeftButton)

    assert requested.count() == 1
    module_id, inputs, config = requested.at(0)
    assert module_id == ModuleId.MOISTURE
    assert inputs == [base.resolve(), raw_one.resolve(), raw_two.resolve()]
    assert config == {
        "schema_version": "1.0",
        "operation": "append_summary",
        "inputs": [
            {"role": "base_summary", "input_index": 0},
            {"role": "new_raw", "input_index": 1},
            {"role": "new_raw", "input_index": 2},
        ],
    }


def test_incremental_entry_is_hidden_without_manifest_declaration(qtbot) -> None:
    page = ModuleTaskPage()
    qtbot.addWidget(page)

    page.set_module(
        ModuleId.MOISTURE,
        "竹丝水分检测",
        [".xlsx"],
        incremental_available=False,
    )

    assert page.operation_combo.isHidden()
    assert page.base_summary_row.isHidden()
