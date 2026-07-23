import importlib
import json
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QAbstractItemView, QLabel, QTableWidget

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.result import FileResult, ModuleResult, ResultSummary
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
    assert table.item(0, 0).text() == "1"
    assert table.item(0, 3).text() == "2026-07-13 10:00:00"
    assert "T" not in table.item(0, 4).text()
    assert table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    headers = [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())]
    assert "error" not in {header.lower() for header in headers}
    assert "result_path" not in {header.lower() for header in headers}


def test_successful_history_row_opens_its_result(
    qtbot, app_context, main_window
) -> None:
    job_id = "history-result"
    task_dir = app_context.paths.tasks / job_id
    output_dir = task_dir / "output-final"
    output_dir.mkdir(parents=True)
    result = ModuleResult.model_validate(
        {
            "schema_version": "1.0",
            "job_id": job_id,
            "module_id": "moisture",
            "module_version": "0.1.1",
            "status": "success",
            "rule_version": "test",
            "summary": {
                "input_count": 1,
                "processed_count": 1,
                "skipped_count": 0,
                "failed_count": 0,
                "anomaly_count": 0,
                "confirmation_count": 0,
            },
            "started_at": datetime.now().astimezone(),
            "finished_at": datetime.now().astimezone(),
        }
    )
    result_path = output_dir / "result.json"
    result_path.write_text(result.model_dump_json(), encoding="utf-8")
    app_context.task_repository.create(
        job_id, "moisture", "success", "2026-07-13T10:00:00+08:00"
    )
    app_context.task_repository.update_status(
        job_id, "success", result_path=str(result_path)
    )
    main_window.history_page.refresh()

    qtbot.mouseClick(
        main_window.history_page.table.viewport(),
        Qt.MouseButton.LeftButton,
        pos=main_window.history_page.table.visualItemRect(
            main_window.history_page.table.item(0, 0)
        ).center(),
    )

    assert main_window.stack.currentWidget() is main_window.result_center_page
    assert main_window.result_center_page.current_result == result


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


def test_missing_real_modules_remain_visible_disabled_placeholders(
    tmp_path, qtbot, monkeypatch
) -> None:
    from app.bootstrap import build_context
    from ui.pages.workbench_page import WorkbenchPage

    empty_modules = tmp_path / "empty-real-modules"
    empty_modules.mkdir()
    monkeypatch.setattr(
        "app.bootstrap.resolve_real_modules_root",
        lambda resource_root, paths: empty_modules,
    )
    context = build_context(tmp_path / "app-data")
    try:
        page = WorkbenchPage(context.registry)
        qtbot.addWidget(page)

        assert set(page.cards) == set(ModuleId)
        assert all("暂未安装" in card.state_label.text() for card in page.cards.values())
        assert all(not card.open_button.isEnabled() for card in page.cards.values())
        assert not hasattr(page, "readiness_bar")
    finally:
        context.close()


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


def test_result_center_expands_public_file_failure_details(qtbot) -> None:
    from ui.pages.result_center_page import ResultCenterPage

    now = datetime.now(UTC)
    result = ModuleResult(
        schema_version="1.0",
        job_id="partial-result",
        module_id=ModuleId.BOILING,
        module_version="1.0.1",
        status=TaskStatus.PARTIAL_SUCCESS,
        summary=ResultSummary(
            input_count=2,
            processed_count=1,
            skipped_count=0,
            failed_count=1,
            anomaly_count=0,
            confirmation_count=0,
        ),
        file_results=[
            FileResult(
                source_file="D:/private/customer/broken.xlsx",
                fingerprint="a" * 64,
                status=TaskStatus.FAILED,
                extracted_records=0,
                anomaly_count=0,
                error="BadZipFile: not a zip file",
            )
        ],
        started_at=now,
        finished_at=now,
    )
    page = ResultCenterPage()
    qtbot.addWidget(page)

    page.show_result(result)
    qtbot.mouseClick(page.failure_toggle, Qt.MouseButton.LeftButton)

    details = " ".join(label.text() for label in page.failure_panel.findChildren(QLabel))
    assert "broken.xlsx" in details
    assert "文件可能已损坏" in details
    assert "D:/private" not in details


def test_result_center_explains_ai_report_degradation(qtbot) -> None:
    from ui.pages.result_center_page import ResultCenterPage

    now = datetime.now(UTC)
    result = ModuleResult(
        schema_version="1.0",
        job_id="ai-degraded",
        module_id=ModuleId.MOISTURE,
        module_version="1.0.1",
        status=TaskStatus.SUCCESS,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            anomaly_count=0,
            confirmation_count=0,
        ),
        errors=["AI_REPORT_DEGRADED: provider_error"],
        started_at=now,
        finished_at=now,
    )
    page = ResultCenterPage()
    qtbot.addWidget(page)

    page.show_result(result)

    assert page.ai_notice.isVisibleTo(page)
    assert "未生成虚假报告" in page.ai_notice.text()


def test_structured_json_business_view_uses_readable_table(qtbot) -> None:
    from ui.widgets.output_files import OutputFilesWidget

    view = OutputFilesWidget._business_view(
        [
            {
                "case_id": "AS-001",
                "customer": "客户甲",
                "issue_types": ["外观", "加工"],
                "needs_review": True,
                "source_cells": {"customer": "B2"},
            }
        ]
    )
    qtbot.addWidget(view)
    table = view.findChild(QTableWidget)

    assert table is not None
    headers = [table.horizontalHeaderItem(index).text() for index in range(table.columnCount())]
    assert "案件编号" in headers
    assert "客户" in headers
    assert "来源文件" not in headers
