import importlib
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QAbstractItemView

from core.contracts.enums import ModuleId
from ui.main_window import MainWindow
from ui.page_ids import PageId


@pytest.fixture
def main_window(qtbot, app_context) -> MainWindow:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    return window


def test_settings_round_trip(qtbot, app_context, main_window) -> None:
    page = main_window.settings_page
    page.output_dir_edit.setText("D:/exports")

    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert app_context.settings.get("output_dir") == "D:/exports"
    assert page.output_dir_edit.accessibleName()
    assert page.save_button.accessibleName()


def test_log_directory_action_is_external_and_nonblocking(
    qtbot,
    app_context,
    main_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[QUrl] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        lambda url: opened.append(url) or True,
    )

    qtbot.mouseClick(
        main_window.settings_page.open_logs_button,
        Qt.MouseButton.LeftButton,
    )

    assert opened == [QUrl.fromLocalFile(str(app_context.paths.logs.resolve()))]
    assert main_window.settings_page.open_logs_button.accessibleName()


def test_history_refreshes_from_repository(app_context, main_window) -> None:
    app_context.task_repository.create(
        "history-1",
        "moisture",
        "success",
        "2026-07-13T10:00:00+08:00",
    )

    main_window.history_page.refresh()

    table = main_window.history_page.table
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "history-1"
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    headers = [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())]
    assert "error" not in {header.lower() for header in headers}
    assert "result_path" not in {header.lower() for header in headers}


def test_navigation_refreshes_history(
    qtbot,
    main_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refreshes: list[None] = []
    monkeypatch.setattr(
        main_window.history_page,
        "refresh",
        lambda: refreshes.append(None),
    )

    qtbot.mouseClick(
        main_window.navigation.buttons[PageId.HISTORY],
        Qt.MouseButton.LeftButton,
    )

    assert refreshes == [None]
    assert main_window.stack.currentWidget() is main_window.history_page


def test_knowledge_placeholder_boundary_is_exact(main_window) -> None:
    page = main_window.knowledge_page

    assert page.namespaces == ("shared", "moisture", "boiling", "after_sales")
    assert page.message == "模拟知识库：真实检索将在公共服务阶段接入"
    assert page.lookup("shared", "竹材") == []
    assert page.lookup("moisture", "含水率") == []
    with pytest.raises(ValueError, match="unknown knowledge namespace"):
        page.lookup("private", "秘密")


def test_secondary_pages_replace_only_canonical_placeholders(main_window) -> None:
    assert list(main_window.pages) == [
        PageId.WORKBENCH,
        PageId.HISTORY,
        PageId.CONFIRMATIONS,
        PageId.KNOWLEDGE,
        PageId.SETTINGS,
    ]
    assert main_window.pages[PageId.HISTORY] is main_window.history_page
    assert main_window.pages[PageId.KNOWLEDGE] is main_window.knowledge_page
    assert main_window.pages[PageId.SETTINGS] is main_window.settings_page


def test_logging_is_rotating_utf8_idempotent_and_redacts_secrets(
    app_context,
) -> None:
    logging_module = importlib.import_module("core.platform.logging")

    logger = logging_module.configure_logging(app_context.paths)
    same_logger = logging_module.configure_logging(app_context.paths)
    application_handlers = [
        handler
        for handler in logger.handlers
        if getattr(handler, "_bamboo_workbench_handler", False)
    ]
    assert logger is same_logger
    assert len(application_handlers) == 1
    handler = application_handlers[0]
    assert isinstance(handler, RotatingFileHandler)
    assert handler.encoding.lower().replace("-", "") == "utf8"

    logger.info("API_KEY=%s", "alpha-secret")
    logger.warning("authorization: Basic beta-secret")
    logger.error("Bearer gamma-secret")
    try:
        raise RuntimeError("api_key=exception-secret")
    except RuntimeError:
        logger.exception("exception path")
    handler.flush()

    content = Path(handler.baseFilename).read_text(encoding="utf-8")
    assert "alpha-secret" not in content
    assert "beta-secret" not in content
    assert "gamma-secret" not in content
    assert "exception-secret" not in content
    assert content.count("[REDACTED]") >= 4


def test_diagnostics_contains_only_allowlisted_nonsecret_fields(
    app_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics_module = importlib.import_module("core.platform.diagnostics")
    app_context.settings.set("api_key", "stored-secret")
    monkeypatch.setenv("AUTHORIZATION", "Bearer environment-secret")

    diagnostics = diagnostics_module.collect_diagnostics(
        app_context.paths,
        app_context.registry,
    )

    assert set(diagnostics) == {
        "application_version",
        "python_version",
        "data_root",
        "modules",
        "log_directory",
    }
    assert {module["module_id"] for module in diagnostics["modules"]} == {
        module_id.value for module_id in ModuleId
    }
    serialized = json.dumps(diagnostics, ensure_ascii=False).lower()
    for forbidden in (
        "stored-secret",
        "environment-secret",
        "api_key",
        "authorization",
        "bearer",
        "token",
    ):
        assert forbidden not in serialized
