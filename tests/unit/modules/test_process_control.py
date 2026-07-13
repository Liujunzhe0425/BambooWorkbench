from unittest.mock import Mock

from PySide6.QtCore import QProcess

from core.modules.process_control import terminate_process


def test_process_cleanup_reports_terminated_host() -> None:
    process = Mock()
    process.state.side_effect = [
        QProcess.ProcessState.Running,
        QProcess.ProcessState.NotRunning,
    ]
    process.waitForFinished.return_value = True

    result = terminate_process(process, grace_ms=100, force_ms=2_000)

    assert result.process_stopped is True
    assert result.detail == "module host terminated"
    process.terminate.assert_called_once_with()
    process.kill.assert_not_called()


def test_process_cleanup_forces_and_reports_stopped_host() -> None:
    process = Mock()
    process.state.side_effect = [
        QProcess.ProcessState.Running,
        QProcess.ProcessState.NotRunning,
    ]
    process.waitForFinished.side_effect = [False, True]

    result = terminate_process(process, grace_ms=100, force_ms=2_000)

    assert result.process_stopped is True
    assert result.detail == "module host killed"
    process.kill.assert_called_once_with()
    assert process.waitForFinished.call_args_list[-1].args == (2_000,)


def test_process_cleanup_reports_host_still_running() -> None:
    process = Mock()
    process.state.side_effect = [
        QProcess.ProcessState.Running,
        QProcess.ProcessState.Running,
    ]
    process.waitForFinished.side_effect = [False, False]

    result = terminate_process(process, grace_ms=100, force_ms=2_000)

    assert result.process_stopped is False
    assert result.detail == "module host cleanup failed"
