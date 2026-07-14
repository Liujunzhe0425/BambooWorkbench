from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QIcon, QPainterPath, QRegion, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.contracts.enums import TaskStatus
from core.contracts.progress import ProgressEvent
from core.contracts.result import ModuleResult
from core.tasks.models import InvalidTaskTransition, TaskLifecycleState
from ui.navigation import Navigation
from ui.page_ids import PageId
from ui.pages.confirmations_page import ConfirmationsPage
from ui.pages.history_page import HistoryPage
from ui.pages.knowledge_page import KnowledgePage
from ui.pages.module_task_page import ModuleTaskPage
from ui.pages.result_center_page import ResultCenterPage
from ui.pages.settings_page import SettingsPage
from ui.pages.task_progress_page import TaskProgressPage
from ui.pages.workbench_page import WorkbenchPage
from ui.widgets.window_title_bar import WindowTitleBar


class MainWindow(QMainWindow):
    _CORNER_RADIUS = 14.0

    def __init__(self, context: object) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("竹简工作台")
        self.setWindowIcon(QIcon(str(context.resource_root / "logo" / "team-logo.png")))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(980, 660)
        self.resize(1180, 760)

        root = QWidget()
        root.setObjectName("appRoot")
        shell_layout = QVBoxLayout(root)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)
        self.title_bar = WindowTitleBar(self)
        shell_layout.addWidget(self.title_bar)

        body = QWidget()
        body.setObjectName("appBody")
        body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        resource_root = context.resource_root
        self.navigation = Navigation(resource_root / "logo" / "team-logo.png")
        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        self.stack.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.workbench_page = WorkbenchPage(context.registry)
        self.history_page = HistoryPage(context.task_repository)
        self.confirmations_page = ConfirmationsPage()
        self.knowledge_page = KnowledgePage(
            context.knowledge_repository,
            context.paths.knowledge,
        )
        self.settings_page = SettingsPage(
            context.settings,
            context.paths,
            context.credential_store,
        )
        self.pages: dict[PageId, QWidget] = {
            PageId.WORKBENCH: self.workbench_page,
            PageId.HISTORY: self.history_page,
            PageId.CONFIRMATIONS: self.confirmations_page,
            PageId.KNOWLEDGE: self.knowledge_page,
            PageId.SETTINGS: self.settings_page,
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.module_task_page = ModuleTaskPage()
        self.task_progress_page = TaskProgressPage()
        self.result_center_page = ResultCenterPage()
        for page in (
            self.module_task_page,
            self.task_progress_page,
            self.result_center_page,
        ):
            self.stack.addWidget(page)

        self.failure_messages: list[QMessageBox] = []
        self._starting_task = False
        self._start_failure_job_id: str | None = None
        self._finalizing_job_id: str | None = None
        self._finalize_failed = False
        self._confirmation_job_ids: set[str] = set()
        self._foreground_job_id: str | None = None

        layout.addWidget(self.navigation)
        layout.addWidget(self.stack, 1)
        shell_layout.addWidget(body, 1)
        self.setCentralWidget(root)
        self.size_grip = QSizeGrip(root)
        self.size_grip.setObjectName("windowSizeGrip")
        self.size_grip.resize(18, 18)
        self.navigation.page_selected.connect(self.navigate)
        self.workbench_page.module_selected.connect(self._open_module)
        self.module_task_page.task_requested.connect(self._start_task)
        self.task_progress_page.cancel_requested.connect(self._cancel_task)
        self.confirmations_page.submitted.connect(self._submit_confirmation)
        self.confirmations_page.job_selected.connect(self._select_confirmation_job)
        self.result_center_page.output_files.open_failed.connect(
            lambda message: self._show_failure("输出文件不可用", message)
        )
        self.settings_page.action_failed.connect(
            lambda message: self._show_failure("设置操作失败", message)
        )
        self.knowledge_page.action_failed.connect(
            lambda message: self._show_failure("知识库操作失败", message)
        )
        context.task_service.progress.connect(self._on_progress)
        context.task_service.needs_confirmation.connect(self._on_confirmation)
        context.task_service.finished.connect(self._on_finished)
        context.task_service.failed.connect(self._on_failed)
        context.task_service.orchestration_error.connect(self._on_orchestration_error)
        context.task_service.status_changed.connect(self._on_status_changed)
        for job_id, result in context.task_service.pending_confirmations():
            self._confirmation_job_ids.add(job_id)
            self.confirmations_page.load(job_id, result.confirmations)
        self.navigate(PageId.WORKBENCH)
        self._apply_window_shape()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        grip_size = self.size_grip.sizeHint()
        self.size_grip.resize(grip_size)
        self.size_grip.move(
            self.centralWidget().width() - grip_size.width(),
            self.centralWidget().height() - grip_size.height(),
        )
        self.size_grip.setVisible(not self.isMaximized())
        self.size_grip.raise_()
        self.title_bar.update_window_state()
        self._apply_window_shape()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() is QEvent.Type.WindowStateChange:
            self._apply_window_shape()

    def _apply_window_shape(self) -> None:
        if self.isMaximized():
            self.clearMask()
            return
        if self.width() <= 0 or self.height() <= 0:
            return
        path = QPainterPath()
        path.addRoundedRect(
            QRectF(self.rect()),
            self._CORNER_RADIUS,
            self._CORNER_RADIUS,
        )
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    @staticmethod
    def _placeholder(page_id: PageId) -> QWidget:
        page = QWidget()
        page.setObjectName(f"page-{page_id.value}")
        return page

    def navigate(self, page_id: PageId) -> None:
        if page_id is PageId.HISTORY:
            self.history_page.refresh()
        self.stack.setCurrentWidget(self.pages[page_id])
        self.navigation.set_current_page(page_id)

    def _cancel_task(self, job_id: str) -> None:
        self.task_progress_page.cancel_button.setEnabled(False)
        try:
            self.context.task_service.cancel(job_id)
        except (InvalidTaskTransition, RuntimeError) as error:
            if self.task_progress_page.current_job_id == job_id:
                self.task_progress_page.cancel_button.setEnabled(True)
            self._show_failure("无法取消任务", str(error))

    def _on_status_changed(
        self,
        job_id: str,
        status: str,
    ) -> None:
        try:
            lifecycle = TaskLifecycleState(status)
        except ValueError:
            return
        if lifecycle is TaskLifecycleState.CANCELLED:
            self._clear_confirmation(job_id)
            if self._is_foreground(job_id):
                self.task_progress_page.current_job_id = ""
                self.task_progress_page.cancel_button.setEnabled(False)
                self.task_progress_page.message_label.setText("任务已取消")
                self._foreground_job_id = None

    def _open_module(self, module_id: object) -> None:
        try:
            module = self.context.registry.get(module_id)
        except KeyError as error:
            self._show_failure("模块不可用", str(error))
            return
        self.module_task_page.set_module(
            module_id,
            module.manifest.module_name,
            module.manifest.supported_extensions,
        )
        self.stack.setCurrentWidget(self.module_task_page)
        self.navigation.set_current_page(PageId.WORKBENCH)

    def _start_task(self, module_id: object, files: list) -> None:
        self._starting_task = True
        self._start_failure_job_id = None
        try:
            job_id = self.context.task_service.create_and_start(module_id, files)
        except Exception as error:
            self._show_failure("任务创建失败", str(error))
            return
        finally:
            self._starting_task = False
        if self._start_failure_job_id == job_id:
            return
        self._foreground_job_id = job_id
        self.task_progress_page.bind(job_id)
        self.stack.setCurrentWidget(self.task_progress_page)

    def _on_progress(self, job_id: str, event: object) -> None:
        if not isinstance(event, ProgressEvent):
            return
        if self._foreground_job_id != job_id:
            return
        if self.task_progress_page.current_job_id != job_id:
            self.task_progress_page.bind(job_id)
        self.task_progress_page.update_progress(event)

    def _on_confirmation(self, job_id: str, result: ModuleResult) -> None:
        self._confirmation_job_ids.add(job_id)
        self.confirmations_page.load(job_id, result.confirmations)
        if self._foreground_job_id == job_id:
            self.confirmations_page.select_job(job_id, user_selected=False)
            self.stack.setCurrentWidget(self.confirmations_page)
            self.navigation.set_current_page(PageId.CONFIRMATIONS)

    def _select_confirmation_job(self, job_id: str) -> None:
        self._foreground_job_id = job_id
        self.stack.setCurrentWidget(self.confirmations_page)
        self.navigation.set_current_page(PageId.CONFIRMATIONS)

    def _submit_confirmation(self, job_id: str, answers: list) -> None:
        self._foreground_job_id = job_id
        self._finalizing_job_id = job_id
        self._finalize_failed = False
        try:
            bundle_path = self.context.confirmation_service.submit(job_id, answers)
            self.context.task_service.finalize(job_id, bundle_path)
        except Exception as error:
            self.confirmations_page.submission_failed(job_id)
            self._show_failure("确认提交失败", str(error))
            return
        finally:
            self._finalizing_job_id = None
        if self._finalize_failed:
            return
        self._clear_confirmation(job_id)
        self.task_progress_page.bind(job_id)
        self.stack.setCurrentWidget(self.task_progress_page)

    def _on_finished(self, result: ModuleResult) -> None:
        self._clear_confirmation(result.job_id)
        if self._foreground_job_id != result.job_id:
            self.history_page.refresh()
            return
        if self.task_progress_page.current_job_id == result.job_id:
            self.task_progress_page.current_job_id = ""
            self.task_progress_page.cancel_button.setEnabled(False)
        self.result_center_page.show_result(result)
        self.stack.setCurrentWidget(self.result_center_page)
        if result.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            self._show_failure("任务未完成", "；".join(result.errors) or result.status.value)
        self._foreground_job_id = None

    def _on_failed(self, job_id: str, message: str) -> None:
        if self._starting_task:
            self._start_failure_job_id = job_id
        if self._finalizing_job_id == job_id:
            self._finalize_failed = True
        was_confirmation = job_id in self._confirmation_job_ids
        self._clear_confirmation(job_id)
        if self._foreground_job_id == job_id:
            target = self.confirmations_page if was_confirmation else self.module_task_page
            self.stack.setCurrentWidget(target)
            self.task_progress_page.current_job_id = ""
            self.task_progress_page.cancel_button.setEnabled(False)
            self.task_progress_page.message_label.setText("任务执行失败")
            self._foreground_job_id = None
        self._show_failure("任务未完成", f"任务 {job_id}：{message}")

    def _on_orchestration_error(self, job_id: str, message: str) -> None:
        if self._starting_task:
            self._start_failure_job_id = job_id
        if self._finalizing_job_id == job_id:
            self._finalize_failed = True
        was_confirmation = job_id in self._confirmation_job_ids
        self._clear_confirmation(job_id)
        if self._foreground_job_id == job_id:
            target = self.confirmations_page if was_confirmation else self.module_task_page
            self.stack.setCurrentWidget(target)
            self.task_progress_page.current_job_id = ""
            self.task_progress_page.cancel_button.setEnabled(False)
            self.task_progress_page.message_label.setText("任务协调错误")
            self._foreground_job_id = None
        self._show_failure("任务协调错误", f"任务 {job_id}：{message}")

    def _clear_confirmation(self, job_id: str) -> None:
        self._confirmation_job_ids.discard(job_id)
        self.confirmations_page.remove(job_id)

    def _is_foreground(self, job_id: str) -> bool:
        return self._foreground_job_id == job_id or (
            self._foreground_job_id is None and self.task_progress_page.current_job_id == job_id
        )

    def _show_failure(self, title: str, message: str) -> None:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        dialog.setModal(False)
        self.failure_messages.append(dialog)
        dialog.show()
