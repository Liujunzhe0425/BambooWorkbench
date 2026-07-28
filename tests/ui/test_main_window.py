from pathlib import Path

from PySide6.QtCore import Qt

from ui.main_window import MainWindow
from ui.page_ids import PageId


def test_main_window_has_canonical_navigation(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert window.windowTitle() == "竹简工作台"
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.windowIcon().isNull() is False
    assert window.title_bar.objectName() == "windowTitleBar"
    assert window.title_bar.version_label.text() == "BambooWorkbench v1.3.4"
    assert window.title_bar.layout().spacing() == 10
    assert window.title_bar.layout().itemAt(0).alignment() & Qt.AlignmentFlag.AlignVCenter
    assert window.title_bar.layout().itemAt(1).alignment() & Qt.AlignmentFlag.AlignVCenter
    assert window.navigation.logo.objectName() == "teamLogo"
    assert window.navigation.logo.pixmap().isNull() is False
    assert list(window.pages) == [
        PageId.WORKBENCH,
        PageId.HISTORY,
        PageId.MONTHLY_HISTORY,
        PageId.CONFIRMATIONS,
        PageId.KNOWLEDGE,
        PageId.SETTINGS,
    ]
    assert window.stack.currentWidget() is window.pages[PageId.WORKBENCH]


def test_navigation_buttons_select_their_canonical_pages(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    for page_id, button in window.navigation.buttons.items():
        qtbot.mouseClick(button, Qt.MouseButton.LeftButton)
        assert button.objectName() == f"navigation-{page_id.value}"
        assert window.stack.currentWidget() is window.pages[page_id]


def test_back_button_returns_to_actual_previous_page(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    window.navigate(PageId.HISTORY)
    window.navigate(PageId.SETTINGS)
    assert not window.back_button.isHidden()

    qtbot.mouseClick(window.back_button, Qt.MouseButton.LeftButton)

    assert window.stack.currentWidget() is window.history_page
    assert window.navigation.buttons[PageId.HISTORY].isChecked()


def test_main_window_uses_the_packaged_logo(app_context) -> None:
    logo_path = app_context.resource_root / "logo" / "team-logo.png"

    assert logo_path == Path(__file__).parents[2] / "logo" / "team-logo.png"
    assert logo_path.is_file()


def test_navigation_exposes_accessible_names_and_descriptions(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert window.navigation.accessibleName() == "主导航"
    assert "竹简工作台" in window.navigation.accessibleDescription()
    assert window.navigation.logo.accessibleName() == "湖南大学智创未来团队标志"
    assert "湖南大学智创未来团队" in window.navigation.logo.accessibleDescription()
    for button in window.navigation.buttons.values():
        assert button.text().endswith(button.accessibleName())
