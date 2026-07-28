import subprocess
from pathlib import Path

import pytest

from core.updates import installer as installer_module


def test_windows_installer_helper_waits_installs_and_relaunches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    install_directory = tmp_path / "installed app"
    install_directory.mkdir()
    update = tmp_path / "BambooWorkbench-Setup-1.3.4.exe"
    application = install_directory / "BambooWorkbench.exe"
    update.write_bytes(b"installer")
    application.write_bytes(b"application")
    calls: list[tuple[list[str], dict[str, object]]] = []
    process = object()

    def fake_popen(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return process

    monkeypatch.setattr(installer_module.sys, "platform", "win32")
    monkeypatch.setattr(installer_module.subprocess, "Popen", fake_popen)

    returned = installer_module.launch_installer_after_exit(
        update,
        tmp_path / "helper",
        parent_pid=321,
        application_path=application,
        install_directory=install_directory,
        expected_version="1.3.4",
    )

    assert returned is process
    arguments, options = calls[0]
    assert arguments[0] == "powershell.exe"
    assert "321" in arguments
    staged_update = tmp_path / "helper" / update.name
    assert str(staged_update) in arguments
    assert staged_update.read_bytes() == b"installer"
    assert str(application) in arguments
    assert str(install_directory) in arguments
    assert "1.3.4" in arguments
    assert "normal" in arguments
    assert str(tmp_path / "helper" / "update-install.log") in arguments
    assert options["creationflags"] == (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    helper = tmp_path / "helper" / "install-update.ps1"
    content = helper.read_text(encoding="utf-8")
    assert "Wait-Process" in content
    assert "Start-Process" in content
    assert "/CLOSEAPPLICATIONS" in content
    assert "/FORCECLOSEAPPLICATIONS" in content
    assert '/DIR=`"$InstallDirectory`"' in content
    assert "module_version -ne $ExpectedVersion" in content
    assert "existing application reopened" in content
    assert "update failed" in content
    assert "application smoke restart completed" in content


def test_windows_installer_helper_rejects_wrong_expected_version(
    tmp_path: Path,
    monkeypatch,
) -> None:
    update = tmp_path / "BambooWorkbench-Setup-1.3.4.exe"
    application = tmp_path / "BambooWorkbench.exe"
    update.write_bytes(b"installer")
    application.write_bytes(b"application")
    monkeypatch.setattr(installer_module.sys, "platform", "win32")

    with pytest.raises(installer_module.UpdateError, match="版本"):
        installer_module.launch_installer_after_exit(
            update,
            tmp_path / "helper",
            application_path=application,
            expected_version="1.3.5",
        )
