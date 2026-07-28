from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QWidget

from core.updates.models import ReleaseUpdate
from ui import updates as updates_module
from ui.updates import UpdateController


def _release(*, size: int = 100 * 1024 * 1024) -> ReleaseUpdate:
    return ReleaseUpdate(
        version="1.3.4",
        tag_name="v1.3.4",
        title="BambooWorkbench v1.3.4",
        notes_url="https://github.com/Liujunzhe0425/BambooWorkbench-Distribution/releases/tag/v1.3.4",
        asset_name="BambooWorkbench-Setup-1.3.4.exe",
        asset_url="https://api.github.com/repos/Liujunzhe0425/BambooWorkbench-Distribution/releases/assets/1",
        asset_size=size,
        sha256="a" * 64,
    )


def _context(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        settings={},
        paths=SimpleNamespace(cache=tmp_path / "cache"),
    )


def test_update_controller_shows_byte_progress_dialog(qtbot, tmp_path: Path) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    controller = UpdateController(parent, _context(tmp_path))
    statuses: list[str] = []
    controller.status_changed.connect(statuses.append)
    release = _release()

    controller._show_download_progress(release)
    dialog = controller._progress_dialog
    assert dialog is not None
    assert dialog.maximum() == release.asset_size
    assert dialog.value() == 0

    controller._download_progressed(25 * 1024 * 1024, release.asset_size)

    assert dialog.value() == 25 * 1024 * 1024
    assert "25.0%" in dialog.labelText()
    assert "25.0/100.0 MB" in dialog.labelText()
    assert "25.0%" in statuses[-1]
    controller._close_download_progress()
    assert controller._progress_dialog is None


def test_downloaded_update_stages_helper_outside_install_and_quits(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    install_directory = tmp_path / "installed"
    install_directory.mkdir()
    application = install_directory / "BambooWorkbench.exe"
    application.write_bytes(b"application")
    installer = tmp_path / "BambooWorkbench-Setup-1.3.4.exe"
    installer.write_bytes(b"installer")
    parent = QWidget()
    qtbot.addWidget(parent)
    controller = UpdateController(parent, _context(tmp_path))
    controller._pending_release = _release(size=installer.stat().st_size)
    launched: dict[str, object] = {}

    def fake_launch(path: Path, helper: Path, **kwargs: object) -> SimpleNamespace:
        launched.update(path=path, helper=helper, **kwargs)
        return SimpleNamespace(pid=99)

    fake_application = SimpleNamespace(quit=lambda: launched.update(quit=True))
    fake_qapplication = SimpleNamespace(instance=lambda: fake_application)
    monkeypatch.setattr(updates_module, "launch_installer_after_exit", fake_launch)
    monkeypatch.setattr(updates_module, "QApplication", fake_qapplication)
    monkeypatch.setattr(updates_module.sys, "executable", str(application))
    monkeypatch.setattr(updates_module.tempfile, "gettempdir", lambda: str(tmp_path / "temp"))

    controller._downloaded(installer)

    assert launched["path"] == installer
    assert launched["application_path"] == application
    assert launched["install_directory"] == install_directory
    assert launched["expected_version"] == "1.3.4"
    assert Path(str(launched["helper"])).parent == tmp_path / "temp" / "BambooWorkbench-updater"
    assert launched["quit"] is True
