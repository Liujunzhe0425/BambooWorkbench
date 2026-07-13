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


def test_knowledge_service_boundary_is_exact(main_window) -> None:
    page = main_window.knowledge_page

    assert page.namespaces == ("shared", "moisture", "boiling", "after_sales")
    assert page.message == "本地知识元数据与确定性检索已启用；当前版本不包含向量检索"
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


def test_logging_redacts_quoted_mapping_json_headers_and_exception_chains(
    app_context,
) -> None:
    logging_module = importlib.import_module("core.platform.logging")
    logger = logging_module.configure_logging(app_context.paths)
    handler = next(
        handler
        for handler in logger.handlers
        if getattr(handler, "_bamboo_workbench_handler", False)
    )

    logger.info({"api_key": "message-secret"})
    logger.info("tuple api_key=%s", "tuple-secret")
    logger.info(
        "mapping authorization=%(credential)s",
        {"credential": "Basic mapping-secret"},
    )
    logger.info('json {"api_key":"json-secret"}')
    logger.warning('headers={"Authorization":"Basic header-secret"}')
    try:
        try:
            raise ValueError("{'api_key': 'inner-exception-secret'}")
        except ValueError as error:
            raise RuntimeError('{"Authorization":"Basic outer-exception-secret"}') from error
    except RuntimeError:
        logger.exception("exception chain")
    handler.flush()

    content = Path(handler.baseFilename).read_text(encoding="utf-8")
    for secret in (
        "message-secret",
        "tuple-secret",
        "mapping-secret",
        "json-secret",
        "header-secret",
        "inner-exception-secret",
        "outer-exception-secret",
    ):
        assert secret not in content


def test_logging_redacts_entire_line_after_sensitive_prefix(
    app_context,
) -> None:
    logging_module = importlib.import_module("core.platform.logging")
    logger = logging_module.configure_logging(app_context.paths)
    handler = next(
        handler
        for handler in logger.handlers
        if getattr(handler, "_bamboo_workbench_handler", False)
    )

    logger.info(r'json {"api_key":"json-prefix\"json-secret-suffix"}')
    logger.info({"api_key": "python-prefix'\"python-secret-suffix"})
    logger.warning(
        'Authorization: Digest username="digest-user-secret", '
        'realm="digest-realm-secret", response="digest-response-secret"'
    )
    logger.warning(
        "headers {'Authorization': 'Custom primary-secret, "
        "secondary=secondary-secret, third=third-secret'}"
    )
    logger.error("Bearer bearer-token-secret, trace=trace-context-secret")
    try:
        try:
            raise ValueError(r'{"api_key":"inner-prefix\"inner-exception-secret"}')
        except ValueError as error:
            raise RuntimeError(
                r"{'Authorization': 'Digest outer-prefix\'outer-exception-secret, "
                r"response=outer-response-secret'}"
            ) from error
    except RuntimeError:
        logger.exception("escaped exception chain")
    handler.flush()

    content = Path(handler.baseFilename).read_text(encoding="utf-8")
    for raw_fragment in (
        "json-prefix",
        "json-secret-suffix",
        "python-prefix",
        "python-secret-suffix",
        "digest-user-secret",
        "digest-realm-secret",
        "digest-response-secret",
        "primary-secret",
        "secondary-secret",
        "third-secret",
        "bearer-token-secret",
        "trace-context-secret",
        "inner-prefix",
        "inner-exception-secret",
        "outer-prefix",
        "outer-exception-secret",
        "outer-response-secret",
    ):
        assert raw_fragment not in content


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


def test_module_card_renders_unknown_health_explicitly(app_context) -> None:
    from dataclasses import replace

    from ui.widgets.module_card import ModuleCard

    module_id = ModuleId.MOISTURE
    app_context.registry._modules[module_id] = replace(
        app_context.registry.get(module_id), health="unknown"
    )
    card = ModuleCard(module_id, "原竹丝水分检测", app_context.registry)

    assert "状态未知" in card.state_label.text()


def test_output_click_rechecks_missing_file_and_never_opens(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from core.contracts.result import OutputArtifact
    from ui.widgets.output_files import OutputFilesWidget

    target = tmp_path / "report.txt"
    target.write_text("ready", encoding="utf-8")
    opened: list[QUrl] = []
    failures: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    widget = OutputFilesWidget()
    qtbot.addWidget(widget)
    widget.open_failed.connect(failures.append)
    widget.set_outputs(
        [
            OutputArtifact(
                type="report",
                path=str(target),
                label="报告",
                mime_type="text/plain",
            )
        ]
    )
    target.unlink()

    qtbot.mouseClick(widget.buttons[0], Qt.MouseButton.LeftButton)

    assert opened == []
    assert failures and "不可用" in failures[0]
