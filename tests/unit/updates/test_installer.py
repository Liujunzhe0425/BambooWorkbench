import subprocess
from pathlib import Path

from core.updates import installer as installer_module


def test_windows_installer_helper_waits_installs_and_relaunches(
    tmp_path: Path,
    monkeypatch,
) -> None:
    update = tmp_path / "BambooWorkbench-Setup-1.2.0.exe"
    application = tmp_path / "BambooWorkbench.exe"
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
    )

    assert returned is process
    arguments, options = calls[0]
    assert arguments[0] == "powershell.exe"
    assert "321" in arguments
    assert str(update) in arguments
    assert str(application) in arguments
    assert options["creationflags"] == (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
    )
    helper = tmp_path / "helper" / "install-update.ps1"
    content = helper.read_text(encoding="utf-8")
    assert "Wait-Process" in content
    assert "Start-Process" in content
    assert "/CLOSEAPPLICATIONS" in content
