import sqlite3
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.bootstrap import build_context, create_application, resolve_resource_root
from core.contracts.enums import ModuleId
from core.modules.registry import ModuleRegistry
from ui.main_window import MainWindow
from ui.page_ids import PageId
from ui.styles.theme import apply_theme


def test_create_application_reuses_the_qt_application(qapp) -> None:
    application = create_application(["bamboo-workbench"])

    assert application is qapp
    assert application.applicationName() == "竹简工作台"


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


def test_resource_root_uses_repository_during_development() -> None:
    assert resolve_resource_root() == Path(__file__).parents[2]


def test_resource_root_uses_pyinstaller_bundle_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "bundle"), raising=False)

    assert resolve_resource_root() == (tmp_path / "bundle").resolve()


def test_theme_applies_approved_visual_identity(qapp, app_context) -> None:
    stylesheet = apply_theme(qapp, app_context.resource_root)

    assert qapp.styleSheet() == stylesheet
    for color in ("#FBFAF4", "#294D3C", "#2FA47D", "#24386F", "#F1B232"):
        assert color in stylesheet
    assert "#navigation" in stylesheet


def test_application_composition_closes_database_on_quit(qapp, app_context) -> None:
    from app.__main__ import compose_application

    connection = app_context.database.connection
    window = compose_application(qapp, app_context)

    assert window.isVisible()
    qapp.aboutToQuit.emit()
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT 1")
