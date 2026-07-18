import sqlite3
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer

from app.bootstrap import (
    build_context,
    create_application,
    resolve_real_modules_root,
    resolve_resource_root,
)
from core.contracts.enums import ModuleId
from core.modules.registry import ModuleRegistry
from ui.main_window import MainWindow
from ui.page_ids import PageId
from ui.styles.theme import apply_theme


def test_create_application_reuses_the_qt_application(qapp) -> None:
    application = create_application(["bamboo-workbench"])

    assert application is qapp
    assert application.applicationName() == "竹简工作台"
    assert application.style().objectName().lower() == "fusion"
    assert application.windowIcon().isNull() is False


def test_build_context_composes_services_and_scans_modules_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, qtbot
) -> None:
    scans = 0
    original_scan = ModuleRegistry.scan

    def counted_scan(registry: ModuleRegistry):
        nonlocal scans
        scans += 1
        return original_scan(registry)

    monkeypatch.setattr(ModuleRegistry, "scan", counted_scan)
    context = build_context(tmp_path / "data", use_mocks=True)
    try:
        assert scans == 1
        assert set(context.scan_results) == {
            ModuleId.MOISTURE,
            ModuleId.BOILING,
            ModuleId.AFTER_SALES,
        }
        assert context.task_service.registry is context.registry
        assert context.confirmation_service.repository is context.confirmation_repository

        window = MainWindow(context)
        qtbot.addWidget(window)
        window.navigate(PageId.SETTINGS)
        qtbot.mouseClick(
            window.navigation.buttons[PageId.WORKBENCH],
            Qt.MouseButton.LeftButton,
        )
        assert scans == 1
    finally:
        context.close()


def test_context_close_releases_the_database(tmp_path: Path) -> None:
    context = build_context(tmp_path / "data", use_mocks=False)
    connection = context.database.connection

    context.close()
    context.close()

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_context_close_shuts_down_tasks_before_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = build_context(tmp_path / "data", use_mocks=False)
    events: list[str] = []
    monkeypatch.setattr(context.task_service, "shutdown", lambda: events.append("tasks"))
    original_close = context.database.close

    def close_database() -> None:
        events.append("database")
        original_close()

    monkeypatch.setattr(context.database, "close", close_database)

    context.close()

    assert events == ["tasks", "database"]


def test_context_close_logs_task_cleanup_failure_and_still_closes_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = build_context(tmp_path / "cleanup-failure", use_mocks=False)
    connection = context.database.connection
    monkeypatch.setattr(context.task_service, "shutdown", lambda: False)

    context.close()

    content = (context.paths.logs / "bamboo-workbench.log").read_text(encoding="utf-8")
    assert "cleanup failure" in content
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_bootstrap_configures_logging_idempotently(tmp_path: Path) -> None:
    first = build_context(tmp_path / "data", use_mocks=False)
    first.close()
    log_path = first.paths.logs / "bamboo-workbench.log"
    content = log_path.read_text(encoding="utf-8")
    assert "application startup" in content
    assert "module scan completed" in content
    assert "task service shutdown complete" in content
    second = build_context(tmp_path / "data", use_mocks=False)
    try:
        handlers = [
            handler
            for handler in second.logger.handlers
            if getattr(handler, "_bamboo_workbench_handler", False)
        ]
        assert len(handlers) == 1
        assert log_path.is_file()
    finally:
        second.close()


def test_resource_root_uses_repository_during_development() -> None:
    assert resolve_resource_root() == Path(__file__).parents[2]


def test_resource_root_uses_pyinstaller_bundle_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    assert resolve_resource_root() == (tmp_path / "bundle").resolve()


def test_real_modules_root_prefers_bundled_modules(tmp_path: Path) -> None:
    from core.platform.paths import AppPaths

    resource_root = tmp_path / "bundle"
    bundled_modules = resource_root / "modules"
    bundled_modules.mkdir(parents=True)
    paths = AppPaths.for_root(tmp_path / "data")

    assert resolve_real_modules_root(resource_root, paths) == bundled_modules


def test_real_modules_root_falls_back_to_local_modules(tmp_path: Path) -> None:
    from core.platform.paths import AppPaths

    resource_root = tmp_path / "bundle"
    paths = AppPaths.for_root(tmp_path / "data")

    assert resolve_real_modules_root(resource_root, paths) == paths.modules


def test_build_context_defaults_to_real_modules(tmp_path: Path) -> None:
    context = build_context(tmp_path / "production-default")
    try:
        assert context.registry.use_mocks is False
    finally:
        context.close()


def test_main_uses_real_modules_by_default_and_mock_only_for_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.__main__ as entrypoint

    selected_modes: list[bool] = []
    application_arguments: list[list[str]] = []

    class SignalProbe:
        def connect(self, callback) -> None:
            self.callback = callback

        def disconnect(self, callback) -> None:
            pass

    class ApplicationProbe:
        aboutToQuit = SignalProbe()

        def setStyleSheet(self, stylesheet: str) -> None:
            pass

        def exec(self) -> int:
            return 0

    class ContextProbe:
        stylesheet = "QMainWindow {}"

        def close(self) -> None:
            pass

    class WindowProbe:
        def __init__(self, context) -> None:
            pass

        def show(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr(
        entrypoint,
        "create_application",
        lambda argv: application_arguments.append(argv) or ApplicationProbe(),
    )
    monkeypatch.setattr(
        entrypoint,
        "build_context",
        lambda *args, **kwargs: selected_modes.append(kwargs["use_mocks"]) or ContextProbe(),
    )
    monkeypatch.setattr(entrypoint, "MainWindow", WindowProbe)

    assert entrypoint.main(["bamboo-workbench"]) == 0
    assert entrypoint.main(["bamboo-workbench", "--demo"]) == 0
    assert selected_modes == [False, True]
    assert application_arguments == [["bamboo-workbench"], ["bamboo-workbench"]]


def test_theme_applies_approved_visual_identity(qapp, app_context) -> None:
    stylesheet = apply_theme(qapp, app_context.resource_root)

    assert qapp.styleSheet() == stylesheet
    for color in ("#FBFAF4", "#294D3C", "#2FA47D", "#24386F", "#F1B232"):
        assert color in stylesheet
    assert "#navigation" in stylesheet
    assert "#windowTitleBar" in stylesheet
    assert "QTableWidget" in stylesheet
    assert "QListWidget" in stylesheet
    assert "QLineEdit" in stylesheet
    assert "#navigation QPushButton:focus" in stylesheet
    assert "border: 2px solid #F1B232" in stylesheet
    checked_rule = stylesheet.split("#navigation QPushButton:checked", 1)[1].split("}", 1)[0]
    primary_rule = stylesheet.split('QPushButton[primary="true"]', 1)[1].split("}", 1)[0]
    assert "background: #FBFAF4" in checked_rule
    assert "color: #294D3C" in checked_rule
    assert "background: #294D3C" in primary_rule
    assert "color: #FFFDF8" in primary_rule


def test_main_lifecycle_closes_database_on_quit(
    qapp, app_context, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.__main__ as entrypoint

    connection = app_context.database.connection
    monkeypatch.setattr(entrypoint, "build_context", lambda *args, **kwargs: app_context)
    QTimer.singleShot(0, qapp.quit)

    assert entrypoint.main(["bamboo-workbench"], use_mocks=False) == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_main_closes_database_when_window_construction_fails(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.__main__ as entrypoint

    context = build_context(tmp_path / "constructor-failure", use_mocks=False)
    connection = context.database.connection
    monkeypatch.setattr(entrypoint, "build_context", lambda *args, **kwargs: context)

    class BrokenWindow:
        def __init__(self, context) -> None:
            raise RuntimeError("window construction failed")

    monkeypatch.setattr(entrypoint, "MainWindow", BrokenWindow)

    with pytest.raises(RuntimeError, match="window construction failed"):
        entrypoint.main(["bamboo-workbench"], use_mocks=False)
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_main_closes_database_when_composition_fails(
    qapp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.__main__ as entrypoint

    context = build_context(tmp_path / "composition-failure", use_mocks=False)
    connection = context.database.connection
    monkeypatch.setattr(entrypoint, "build_context", lambda *args, **kwargs: context)
    monkeypatch.setattr(
        entrypoint,
        "compose_application",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("compose failed")),
    )

    with pytest.raises(RuntimeError, match="compose failed"):
        entrypoint.main(["bamboo-workbench"], use_mocks=False)
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")


def test_repeated_main_lifecycles_disconnect_quit_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.__main__ as entrypoint

    class SignalProbe:
        def __init__(self) -> None:
            self.callbacks = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

        def disconnect(self, callback) -> None:
            self.callbacks.remove(callback)

        def emit(self) -> None:
            for callback in tuple(self.callbacks):
                callback()

    class ApplicationProbe:
        def __init__(self) -> None:
            self.aboutToQuit = SignalProbe()

        def setStyleSheet(self, stylesheet: str) -> None:
            self.stylesheet = stylesheet

        def exec(self) -> int:
            self.aboutToQuit.emit()
            return 0

    class ContextProbe:
        stylesheet = "QMainWindow {}"
        close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class WindowProbe:
        def __init__(self, context) -> None:
            self.visible = False
            self.closed = False

        def show(self) -> None:
            self.visible = True

        def close(self) -> None:
            self.closed = True

    application = ApplicationProbe()
    contexts = [ContextProbe(), ContextProbe()]
    monkeypatch.setattr(entrypoint, "create_application", lambda argv=None: application)
    monkeypatch.setattr(entrypoint, "build_context", lambda *args, **kwargs: contexts.pop(0))
    monkeypatch.setattr(entrypoint, "MainWindow", WindowProbe)

    assert entrypoint.main(["first"], use_mocks=False) == 0
    assert application.aboutToQuit.callbacks == []
    assert entrypoint.main(["second"], use_mocks=False) == 0
    assert application.aboutToQuit.callbacks == []


def test_main_closes_context_when_signal_teardown_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.__main__ as entrypoint

    class BrokenSignal:
        def connect(self, callback) -> None:
            pass

        def disconnect(self, callback) -> None:
            raise RuntimeError("disconnect failed")

    class ApplicationProbe:
        aboutToQuit = BrokenSignal()

        def setStyleSheet(self, stylesheet: str) -> None:
            pass

        def exec(self) -> int:
            return 0

    class ContextProbe:
        stylesheet = "QMainWindow {}"

        def __init__(self) -> None:
            self.close_calls = 0

        def close(self) -> None:
            self.close_calls += 1

    class WindowProbe:
        def __init__(self, context) -> None:
            pass

        def show(self) -> None:
            pass

        def close(self) -> None:
            pass

    context = ContextProbe()
    monkeypatch.setattr(entrypoint, "create_application", lambda argv=None: ApplicationProbe())
    monkeypatch.setattr(entrypoint, "build_context", lambda *args, **kwargs: context)
    monkeypatch.setattr(entrypoint, "MainWindow", WindowProbe)

    with pytest.raises(RuntimeError, match="disconnect failed"):
        entrypoint.main(["bamboo-workbench"], use_mocks=False)
    assert context.close_calls == 1
