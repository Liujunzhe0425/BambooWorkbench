from types import SimpleNamespace

from PySide6.QtCore import QSize, Qt

from ui.main_window import MainWindow
from ui.page_ids import PageId


def test_visual_shell_uses_distinct_sidebar_and_light_content(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.setStyleSheet(app_context.stylesheet)
    window.show()
    qtbot.wait(20)

    assert window.navigation.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert window.stack.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert window.navigation.width() == 210
    assert window.stack.width() > window.navigation.width()
    assert window.centralWidget().layout().contentsMargins().left() == 0
    assert window.mask().isEmpty()

    buttons = (
        window.title_bar.minimize_button,
        window.title_bar.maximize_button,
        window.title_bar.close_button,
    )
    assert {button.size() for button in buttons} == {QSize(40, 40)}
    assert [button.control_kind for button in buttons] == [
        "minimize",
        "maximize",
        "close",
    ]


def test_native_rounded_corners_request_is_sent_to_dwm(
    qtbot, app_context, monkeypatch
) -> None:
    calls: list[tuple[object, ...]] = []

    def set_window_attribute(*args) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(
        "ui.main_window.ctypes.windll",
        SimpleNamespace(
            dwmapi=SimpleNamespace(DwmSetWindowAttribute=set_window_attribute)
        ),
    )

    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert window._enable_native_rounded_corners() is True
    assert len(calls) == 1
    assert calls[0][1] == 33


def test_all_primary_pages_share_the_designed_page_shell(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    for page_id in PageId:
        window.navigate(page_id)
        page = window.stack.currentWidget()
        assert page.objectName().startswith("page-")
        assert page.layout().contentsMargins().left() == 30
