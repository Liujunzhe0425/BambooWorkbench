import subprocess
import sys
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QProcess

from core.modules import process_control
from core.modules.process_control import TaskkillAttempt, terminate_process_tree


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree behavior")
def test_windows_cleanup_reports_forced_tree_success(
    monkeypatch,
) -> None:
    process = Mock()
    process.state.side_effect = [
        QProcess.ProcessState.Running,
        QProcess.ProcessState.NotRunning,
    ]
    process.processId.return_value = 1234
    process.waitForFinished.return_value = True
    attempts = iter(
        [
            TaskkillAttempt(False, "graceful taskkill exited with code 1"),
            TaskkillAttempt(True, "forced taskkill succeeded"),
        ]
    )
    monkeypatch.setattr(process_control, "_run_taskkill", lambda *args, **kwargs: next(attempts))

    result = terminate_process_tree(process, grace_ms=100, force_ms=2_000)

    assert result.process_stopped is True
    assert result.tree_terminated is True
    assert result.detail == "forced taskkill succeeded"
    process.waitForFinished.assert_called_once_with(2_000)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process-tree behavior")
def test_windows_cleanup_reports_direct_fallback_as_unconfirmed_tree(
    monkeypatch,
) -> None:
    process = Mock()
    process.state.side_effect = [
        QProcess.ProcessState.Running,
        QProcess.ProcessState.Running,
        QProcess.ProcessState.NotRunning,
    ]
    process.processId.return_value = 1234
    process.waitForFinished.return_value = True
    attempts = iter(
        [
            TaskkillAttempt(False, "graceful taskkill timed out"),
            TaskkillAttempt(False, "forced taskkill exited with code 5"),
        ]
    )
    monkeypatch.setattr(process_control, "_run_taskkill", lambda *args, **kwargs: next(attempts))

    result = terminate_process_tree(process, grace_ms=100, force_ms=2_000)

    assert result.process_stopped is True
    assert result.tree_terminated is False
    assert "forced taskkill exited with code 5" in result.detail
    assert "direct process stopped" in result.detail


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskkill behavior")
def test_taskkill_timeout_is_reported_and_uses_no_console(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def timeout_run(*args, **kwargs):
        captured.update(kwargs)
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(process_control.subprocess, "run", timeout_run)

    result = process_control._run_taskkill(1234, force=True, timeout_ms=2_000)

    assert result.succeeded is False
    assert result.detail == "forced taskkill timed out after 2000 ms"
    assert captured["creationflags"] == subprocess.CREATE_NO_WINDOW


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskkill behavior")
def test_taskkill_nonzero_exit_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(
        process_control.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=5, stdout=b"", stderr=b"access denied"
        ),
    )

    result = process_control._run_taskkill(1234, force=False, timeout_ms=500)

    assert result.succeeded is False
    assert result.detail == "graceful taskkill exited with code 5: access denied"
