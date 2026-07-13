import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.modules.process_host import HOST_SETUP_ERROR, JobSetupError, run_host


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object")
def test_job_setup_failure_spawns_no_module_child(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    launcher = tmp_path / "run_module.cmd"
    launcher.write_text("@echo off\r\necho must-not-run\r\n", encoding="utf-8")
    child_runner = Mock()

    def fail_job_setup():
        raise JobSetupError("simulated assignment failure")

    result = run_host(
        launcher,
        ["self-check"],
        job_factory=fail_job_setup,
        child_runner=child_runner,
    )

    assert result == HOST_SETUP_ERROR
    assert capsys.readouterr().err == (
        "module host job setup failed: simulated assignment failure\n"
    )
    child_runner.assert_not_called()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object")
def test_normal_child_exit_terminates_host_with_child_code(tmp_path: Path) -> None:
    launcher = tmp_path / "run_module.cmd"
    launcher.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")

    class HostExited(Exception):
        pass

    exit_codes: list[int] = []

    def host_exit(exit_code: int) -> None:
        exit_codes.append(exit_code)
        raise HostExited

    child_runner = Mock(
        return_value=subprocess.CompletedProcess(args=[], returncode=7)
    )

    with pytest.raises(HostExited):
        run_host(
            launcher,
            ["self-check"],
            job_factory=lambda: object(),
            child_runner=child_runner,
            host_exit=host_exit,
        )

    assert exit_codes == [7]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object")
def test_host_keeps_launcher_and_arguments_out_of_cmd_text(tmp_path: Path) -> None:
    special_dir = tmp_path / "模块 & %PATH% ^ (space) !"
    special_dir.mkdir()
    launcher = special_dir / "run_module.cmd"
    launcher.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    job_path = special_dir / "任务 & %PATH% ^ (job).json"
    job_path.write_text("{}", encoding="utf-8")
    captured: dict[str, object] = {}

    class HostExited(Exception):
        pass

    def child_runner(command: str, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0)

    with pytest.raises(HostExited):
        run_host(
            launcher,
            ["run", "--job", str(job_path)],
            job_factory=lambda: object(),
            child_runner=child_runner,
            host_exit=lambda _code: (_ for _ in ()).throw(HostExited),
        )

    command = str(captured["command"])
    environment = captured["env"]
    assert str(launcher) not in command
    assert str(job_path) not in command
    assert "/v:off" in command
    assert environment["BAMBOO_HOST_LAUNCHER"] == str(launcher.resolve())
    assert environment["BAMBOO_HOST_ARG_2"] == str(job_path)
