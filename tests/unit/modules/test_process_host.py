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
