from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.progress import ProgressEvent
from core.contracts.result import (
    ConfirmationPrompt,
    ModuleResult,
    OutputArtifact,
    ResultSummary,
    SourceRef,
)
from ui.main_window import MainWindow
from ui.page_ids import PageId

JOURNEY_TIMEOUT_MS = 15_000


def _pump_application_until_terminal(
    application: QApplication,
    expected: QSignalSpy,
    failures: QSignalSpy,
    signals: list[object],
) -> None:
    if expected.count() + failures.count() > 0:
        return
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(application.quit)
    for signal in signals:
        signal.connect(application.quit)
    try:
        timeout.start(JOURNEY_TIMEOUT_MS)
        application.exec()
    finally:
        for signal in signals:
            signal.disconnect(application.quit)
    assert expected.count() + failures.count() > 0


class _DropEvent:
    def __init__(self, paths: list[Path]) -> None:
        self._mime_data = QMimeData()
        self._mime_data.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.accepted = False

    def mimeData(self) -> QMimeData:
        return self._mime_data

    def acceptProposedAction(self) -> None:
        self.accepted = True


class _ConcurrentRunner(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.cancel_calls = 0

    def start(self, _module: object, _job_path: Path) -> None:
        pass

    def cancel(self) -> bool:
        self.cancel_calls += 1
        return True


def _result(output_path: Path) -> ModuleResult:
    now = datetime.now(UTC)
    return ModuleResult(
        schema_version="1.0",
        job_id="result-job-001",
        module_id=ModuleId.MOISTURE,
        module_version="0.1.0",
        status=TaskStatus.SUCCESS,
        summary=ResultSummary(
            input_count=1,
            processed_count=1,
            skipped_count=0,
            failed_count=0,
            anomaly_count=0,
            confirmation_count=0,
        ),
        outputs=[
            OutputArtifact(
                type="report",
                path=str(output_path),
                label="结果报告",
                mime_type="text/plain",
            )
        ],
        started_at=now,
        finished_at=now,
    )


def test_main_window_keeps_canonical_pages_separate_from_internal_workflow_pages(
    qtbot, app_context
) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert list(window.pages) == [
        PageId.WORKBENCH,
        PageId.HISTORY,
        PageId.CONFIRMATIONS,
        PageId.KNOWLEDGE,
        PageId.SETTINGS,
    ]
    assert window.pages[PageId.WORKBENCH] is window.workbench_page
    assert window.pages[PageId.CONFIRMATIONS] is window.confirmations_page
    assert window.module_task_page not in window.pages.values()
    assert window.task_progress_page not in window.pages.values()
    assert window.result_center_page not in window.pages.values()
    assert window.stack.indexOf(window.module_task_page) >= len(window.pages)


def test_workbench_uses_exact_identity_and_reports_module_state(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    assert window.workbench_page.company_label.text() == "湖南桃花江竹材科技股份有限公司"
    assert window.workbench_page.product_label.text() == "竹简工作台"
    assert set(window.workbench_page.cards) == set(ModuleId)
    for card in window.workbench_page.cards.values():
        assert "已安装" in card.state_label.text()
        assert "模拟模块" in card.state_label.text()
        assert "健康" in card.state_label.text()
        assert card.accessibleName()


def test_intake_filters_deduplicates_drop_and_supports_remove_and_clear(
    qtbot, app_context, tmp_path: Path
) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    page = window.module_task_page
    page.set_module(ModuleId.MOISTURE, "原竹丝水分检测", [".xlsx"])
    first = tmp_path / "first.xlsx"
    second = tmp_path / "SECOND.XLSX"
    unsupported = tmp_path / "notes.csv"
    for path in (first, second, unsupported):
        path.write_bytes(b"input")

    event = _DropEvent([first, first, second, unsupported])
    page.file_drop_zone.dropEvent(event)

    assert event.accepted
    assert page.files == [first.resolve(), second.resolve()]
    assert page.file_list.count() == 2
    assert "已忽略 1" in page.intake_feedback.text()
    page.file_list.setCurrentRow(0)
    qtbot.mouseClick(page.remove_button, Qt.MouseButton.LeftButton)
    assert page.files == [second.resolve()]
    qtbot.mouseClick(page.clear_button, Qt.MouseButton.LeftButton)
    assert page.files == []
    assert not page.run_button.isEnabled()


def test_file_and_folder_pickers_share_the_same_intake_boundary(
    qtbot, app_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    page = window.module_task_page
    page.set_module(ModuleId.BOILING, "水煮实验", [".xlsx"])
    picked = tmp_path / "picked.xlsx"
    folder = tmp_path / "folder"
    nested = folder / "nested"
    nested.mkdir(parents=True)
    from_folder = nested / "batch.xlsx"
    unsupported = folder / "ignore.txt"
    for path in (picked, from_folder, unsupported):
        path.write_bytes(b"input")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *args, **kwargs: ([str(picked), str(unsupported)], ""),
    )
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(folder),
    )

    qtbot.mouseClick(page.add_files_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(page.add_folder_button, Qt.MouseButton.LeftButton)

    assert page.files == [picked.resolve(), from_folder.resolve()]
    assert all(path.suffix.lower() == ".xlsx" for path in page.files)


def test_progress_page_updates_and_exposes_cancel_request_only(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    page = window.task_progress_page
    cancelled = QSignalSpy(page.cancel_requested)

    page.bind("progress-job-001")
    page.update_progress(ProgressEvent(type="progress", percent=37, message="正在处理"))
    qtbot.mouseClick(page.cancel_button, Qt.MouseButton.LeftButton)

    assert page.progress_bar.value() == 37
    assert page.message_label.text() == "正在处理"
    assert cancelled.count() == 1
    assert cancelled.at(0) == ["progress-job-001"]
    assert page.cancel_button.accessibleName() == "取消当前任务"


def test_result_page_opens_only_existing_validated_output_artifacts(
    qtbot, app_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = tmp_path / "report.txt"
    existing.write_text("result", encoding="utf-8")
    opened: list[QUrl] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url) or True)
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    result = _result(existing)
    result.outputs.append(
        OutputArtifact(
            type="report",
            path=str(tmp_path / "missing.txt"),
            label="不存在的报告",
            mime_type="text/plain",
        )
    )
    window.result_center_page.show_result(result)
    assert window.result_center_page.current_result.status is TaskStatus.SUCCESS
    assert len(window.result_center_page.output_buttons) == 1
    button = window.result_center_page.output_buttons[0]
    assert button.accessibleName() == "打开结果报告"
    qtbot.mouseClick(button, Qt.MouseButton.LeftButton)

    assert opened == [QUrl.fromLocalFile(str(existing.resolve()))]


def test_successful_mock_journey(qtbot, qapp, app_context, tmp_path: Path) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.show()

    window.workbench_page.module_selected.emit(ModuleId.MOISTURE)
    assert window.stack.currentWidget() is window.module_task_page
    window.module_task_page.add_files([source])
    finished = QSignalSpy(app_context.task_service.finished)
    failures = QSignalSpy(app_context.task_service.failed)
    qtbot.mouseClick(window.module_task_page.run_button, Qt.MouseButton.LeftButton)
    _pump_application_until_terminal(
        qapp,
        finished,
        failures,
        [app_context.task_service.finished, app_context.task_service.failed],
    )
    assert failures.count() == 0, failures.at(0) if failures.count() else None

    assert window.stack.currentWidget() is window.result_center_page
    assert window.result_center_page.current_result.status is TaskStatus.SUCCESS
    assert window.result_center_page.output_buttons


def test_confirmation_ui_submits_and_finalizes_real_mock_journey(
    qtbot, qapp, app_context, tmp_path: Path
) -> None:
    source = tmp_path / "confirm.xlsx"
    source.write_bytes(b"mock")
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.show()
    window.workbench_page.module_selected.emit(ModuleId.MOISTURE)
    window.module_task_page.add_files([source])

    needs_confirmation = QSignalSpy(app_context.task_service.needs_confirmation)
    failures = QSignalSpy(app_context.task_service.failed)
    qtbot.mouseClick(window.module_task_page.run_button, Qt.MouseButton.LeftButton)
    _pump_application_until_terminal(
        qapp,
        needs_confirmation,
        failures,
        [
            app_context.task_service.needs_confirmation,
            app_context.task_service.failed,
        ],
    )
    assert failures.count() == 0, failures.at(0) if failures.count() else None
    assert window.stack.currentWidget() is window.confirmations_page
    assert window.confirmations_page.current_job_id
    assert window.confirmations_page.answer_inputs["mock-confirm-1"].accessibleName()

    finished = QSignalSpy(app_context.task_service.finished)
    qtbot.mouseClick(
        window.confirmations_page.submit_button,
        Qt.MouseButton.LeftButton,
    )
    _pump_application_until_terminal(
        qapp,
        finished,
        failures,
        [app_context.task_service.finished, app_context.task_service.failed],
    )
    assert failures.count() == 0, failures.at(0) if failures.count() else None

    assert window.stack.currentWidget() is window.result_center_page
    assert window.result_center_page.current_result.status is TaskStatus.SUCCESS


def test_task_failure_is_nonblocking_and_keeps_window_usable(
    qtbot, app_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "empty.xlsx"
    source.touch()
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("modal dialog used")),
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.show()
    window.workbench_page.module_selected.emit(ModuleId.MOISTURE)
    window.module_task_page.add_files([source])

    with qtbot.waitSignal(app_context.task_service.failed, timeout=5_000):
        qtbot.mouseClick(window.module_task_page.run_button, Qt.MouseButton.LeftButton)

    assert window.failure_messages
    message = window.failure_messages[-1]
    assert message.isModal() is False
    assert "任务未完成" in message.windowTitle()
    assert message.isVisible()
    assert window.stack.currentWidget() is window.module_task_page
    window.navigate(PageId.WORKBENCH)
    assert window.stack.currentWidget() is window.workbench_page


def test_pre_start_exception_is_nonblocking_and_keeps_task_page(
    qtbot, app_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "normal.xlsx"
    source.write_bytes(b"mock")
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.workbench_page.module_selected.emit(ModuleId.MOISTURE)
    window.module_task_page.add_files([source])
    monkeypatch.setattr(
        app_context.task_service,
        "create_and_start",
        lambda *args: (_ for _ in ()).throw(OSError("无法创建任务目录")),
    )

    qtbot.mouseClick(window.module_task_page.run_button, Qt.MouseButton.LeftButton)

    assert window.failure_messages
    assert "任务创建失败" in window.failure_messages[-1].windowTitle()
    assert window.stack.currentWidget() is window.module_task_page


def test_finalize_exception_keeps_confirmation_page_active(
    qtbot, app_context, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompt = ConfirmationPrompt(
        confirmation_id="confirm-ui-1",
        field="mock_field",
        reason="需要人工确认",
        suggested_value="建议值",
        options=["建议值"],
        confidence=0.5,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file=str(tmp_path / "source.xlsx")),
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window.confirmations_page.load("confirm-job-001", [prompt])
    window.stack.setCurrentWidget(window.confirmations_page)
    bundle = tmp_path / "confirmation.json"
    monkeypatch.setattr(
        app_context.confirmation_service,
        "submit",
        lambda *args: bundle,
    )
    monkeypatch.setattr(
        app_context.task_service,
        "finalize",
        lambda *args: (_ for _ in ()).throw(RuntimeError("无法启动确认任务")),
    )

    qtbot.mouseClick(window.confirmations_page.submit_button, Qt.MouseButton.LeftButton)

    assert window.failure_messages
    assert "确认提交失败" in window.failure_messages[-1].windowTitle()
    assert window.stack.currentWidget() is window.confirmations_page


def test_workflow_controls_expose_keyboard_accessibility_metadata(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)

    controls = [
        window.module_task_page.file_drop_zone,
        window.module_task_page.file_list,
        window.module_task_page.add_files_button,
        window.module_task_page.add_folder_button,
        window.module_task_page.remove_button,
        window.module_task_page.clear_button,
        window.module_task_page.run_button,
        window.confirmations_page.submit_button,
        window.task_progress_page.progress_bar,
        window.task_progress_page.cancel_button,
    ]
    assert all(control.accessibleName() for control in controls)
    assert window.module_task_page.run_button.focusPolicy() is not Qt.FocusPolicy.NoFocus
    assert window.confirmations_page.submit_button.focusPolicy() is not Qt.FocusPolicy.NoFocus


def test_background_job_events_do_not_replace_foreground_workflow(
    qtbot, app_context, tmp_path: Path
) -> None:
    first_output = tmp_path / "first.txt"
    first_output.write_text("first", encoding="utf-8")
    second_output = tmp_path / "second.txt"
    second_output.write_text("second", encoding="utf-8")
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._foreground_job_id = "foreground-job"
    window.task_progress_page.bind("foreground-job")
    window.stack.setCurrentWidget(window.task_progress_page)

    window._on_progress(
        "background-job",
        ProgressEvent(type="progress", percent=91, message="后台进度"),
    )
    window._on_finished(_result(second_output).model_copy(update={"job_id": "background-job"}))

    assert window.task_progress_page.current_job_id == "foreground-job"
    assert window.stack.currentWidget() is window.task_progress_page
    assert window.result_center_page.current_result is None

    foreground = _result(first_output).model_copy(update={"job_id": "foreground-job"})
    window._on_finished(foreground)

    assert window.stack.currentWidget() is window.result_center_page
    assert window.result_center_page.current_result == foreground


def test_multiple_confirmation_models_are_isolated_and_selection_sets_foreground(
    qtbot, app_context, tmp_path: Path
) -> None:
    prompt_one = ConfirmationPrompt(
        confirmation_id="confirm-one",
        field="field_one",
        reason="reason one",
        suggested_value="one",
        options=["one"],
        confidence=0.8,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file=str(tmp_path / "one.xlsx")),
    )
    prompt_two = prompt_one.model_copy(
        update={"confirmation_id": "confirm-two", "field": "field_two"}
    )
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._foreground_job_id = "job-one"
    summary = ResultSummary(
        input_count=1,
        processed_count=0,
        skipped_count=0,
        failed_count=0,
        anomaly_count=0,
        confirmation_count=1,
    )
    first = _result(tmp_path / "unused-one.txt").model_copy(
        update={
            "job_id": "job-one",
            "status": TaskStatus.NEEDS_CONFIRMATION,
            "confirmations": [prompt_one],
            "summary": summary,
            "outputs": [],
        }
    )
    second = first.model_copy(update={"job_id": "job-two", "confirmations": [prompt_two]})

    window._on_confirmation("job-one", first)
    window._on_confirmation("job-two", second)

    assert set(window.confirmations_page.pending_job_ids) == {"job-one", "job-two"}
    assert window.confirmations_page.current_job_id == "job-one"
    assert "confirm-one" in window.confirmations_page.answer_inputs
    assert "confirm-two" not in window.confirmations_page.answer_inputs

    window.confirmations_page.select_job("job-two")

    assert window._foreground_job_id == "job-two"
    assert window.confirmations_page.current_job_id == "job-two"
    assert "confirm-two" in window.confirmations_page.answer_inputs


def test_background_cancel_does_not_clear_foreground_progress(qtbot, app_context) -> None:
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._foreground_job_id = "foreground-job"
    window.task_progress_page.bind("foreground-job")
    window.stack.setCurrentWidget(window.task_progress_page)
    window.confirmations_page.load("background-job", [])
    window._confirmation_job_ids.add("background-job")

    window._on_status_changed("background-job", "cancelled")

    assert window._foreground_job_id == "foreground-job"
    assert window.task_progress_page.current_job_id == "foreground-job"
    assert window.stack.currentWidget() is window.task_progress_page
    assert "background-job" not in window.confirmations_page.pending_job_ids


def test_two_fake_jobs_interleave_progress_cancel_and_finish_without_ui_crosstalk(
    qtbot, app_context, tmp_path: Path
) -> None:
    runners: list[_ConcurrentRunner] = []

    def runner_factory() -> _ConcurrentRunner:
        runner = _ConcurrentRunner()
        runners.append(runner)
        return runner

    app_context.task_service.runner_factory = runner_factory
    first_source = tmp_path / "first.xlsx"
    second_source = tmp_path / "second.xlsx"
    first_source.write_bytes(b"first")
    second_source.write_bytes(b"second")
    first_output = tmp_path / "first-result.txt"
    first_output.write_text("first", encoding="utf-8")
    first_job = app_context.task_service.create_and_start(ModuleId.MOISTURE, [first_source])
    second_job = app_context.task_service.create_and_start(ModuleId.MOISTURE, [second_source])
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._foreground_job_id = first_job
    window.task_progress_page.bind(first_job)
    window.stack.setCurrentWidget(window.task_progress_page)

    runners[1].progress.emit(ProgressEvent(type="progress", percent=90, message="后台进度"))
    runners[0].progress.emit(ProgressEvent(type="progress", percent=30, message="前台进度"))
    app_context.task_service.cancel(second_job)
    runners[1].cancelled.emit()
    runners[0].completed.emit(_result(first_output).model_copy(update={"job_id": first_job}))

    assert runners[1].cancel_calls == 1
    assert app_context.task_repository.get(second_job)["status"] == "cancelled"
    assert window.result_center_page.current_result.job_id == first_job
    assert window.stack.currentWidget() is window.result_center_page


def test_two_fake_jobs_interleave_confirmations_without_overwriting_foreground(
    qtbot, app_context, tmp_path: Path
) -> None:
    runners: list[_ConcurrentRunner] = []

    def runner_factory() -> _ConcurrentRunner:
        runner = _ConcurrentRunner()
        runners.append(runner)
        return runner

    app_context.task_service.runner_factory = runner_factory
    sources = [tmp_path / "one.xlsx", tmp_path / "two.xlsx"]
    for source in sources:
        source.write_bytes(b"mock")
    jobs = [
        app_context.task_service.create_and_start(ModuleId.MOISTURE, [source]) for source in sources
    ]
    window = MainWindow(app_context)
    qtbot.addWidget(window)
    window._foreground_job_id = jobs[0]
    prompt = ConfirmationPrompt(
        confirmation_id="confirm-one",
        field="field_one",
        reason="reason",
        suggested_value="one",
        options=["one"],
        confidence=0.8,
        blocking=True,
        batch_applicable=False,
        rememberable=False,
        source=SourceRef(source_file=str(sources[0])),
    )
    summary = ResultSummary(
        input_count=1,
        processed_count=0,
        skipped_count=0,
        failed_count=0,
        anomaly_count=0,
        confirmation_count=1,
    )
    first = _result(tmp_path / "unused.txt").model_copy(
        update={
            "job_id": jobs[0],
            "status": TaskStatus.NEEDS_CONFIRMATION,
            "confirmations": [prompt],
            "summary": summary,
            "outputs": [],
        }
    )
    second_prompt = prompt.model_copy(
        update={"confirmation_id": "confirm-two", "field": "field_two"}
    )
    second = first.model_copy(update={"job_id": jobs[1], "confirmations": [second_prompt]})

    runners[0].completed.emit(first)
    runners[1].completed.emit(second)

    assert window.confirmations_page.current_job_id == jobs[0]
    assert "confirm-one" in window.confirmations_page.answer_inputs
    assert "confirm-two" not in window.confirmations_page.answer_inputs
    assert set(window.confirmations_page.pending_job_ids) == set(jobs)
