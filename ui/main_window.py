import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.contracts.enums import ModuleId, TaskStatus
from core.contracts.progress import ProgressEvent
from core.contracts.result import ModuleResult
from core.platform.path_safety import resolve_contained_file
from core.tasks.models import InvalidTaskTransition, TaskLifecycleState
from core.tasks.result_status import normalized_result
from ui.navigation import Navigation
from ui.page_ids import PageId
from ui.pages.after_sales_ai_setup_page import AfterSalesAiSetupPage
from ui.pages.confirmations_page import ConfirmationsPage
from ui.pages.history_page import HistoryPage
from ui.pages.knowledge_page import KnowledgePage
from ui.pages.module_task_page import ModuleTaskPage
from ui.pages.moisture_ai_report_page import MoistureAIReportPage
from ui.pages.moisture_governance_page import MoistureGovernancePage
from ui.pages.result_center_page import ResultCenterPage
from ui.pages.settings_page import SettingsPage
from ui.pages.task_progress_page import TaskProgressPage
from ui.pages.workbench_page import WorkbenchPage
from ui.updates import UpdateController
from ui.widgets.window_title_bar import WindowTitleBar


class MainWindow(QMainWindow):
    def __init__(self, context: object) -> None:
        super().__init__()
        self.context = context
        self.setWindowTitle("竹简工作台")
        self.setWindowIcon(QIcon(str(context.resource_root / "logo" / "team-logo.png")))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
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
        self.history_page = HistoryPage(
            context.task_repository,
            status_resolver=self._historical_status,
        )
        self.confirmations_page = ConfirmationsPage(context.task_repository.get_number)
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
        self.moisture_ai_report_page = MoistureAIReportPage(
            context.module_management_service,
            context.settings,
        )
        self.moisture_governance_page = MoistureGovernancePage(
            context.module_management_service
        )
        self.after_sales_ai_setup_page = AfterSalesAiSetupPage(
            context.settings,
            context.credential_store,
            context.reload_ai_configuration,
        )
        for page in (
            self.module_task_page,
            self.task_progress_page,
            self.result_center_page,
            self.moisture_ai_report_page,
            self.moisture_governance_page,
            self.after_sales_ai_setup_page,
        ):
            self.stack.addWidget(page)

        self.failure_messages: list[QMessageBox] = []
        self._starting_task = False
        self._start_failure_job_id: str | None = None
        self._finalizing_job_id: str | None = None
        self._finalize_failed = False
        self._confirmation_job_ids: set[str] = set()
        self._foreground_job_id: str | None = None
        self._after_sales_ai_ready = False
        self._navigation_history: list[tuple[QWidget, PageId]] = []
        self._current_nav_page = PageId.WORKBENCH

        page_host = QWidget()
        page_host.setObjectName("pageHost")
        page_layout = QVBoxLayout(page_host)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)
        self.back_button = QPushButton("←  返回")
        self.back_button.setObjectName("pageBackButton")
        self.back_button.setProperty("secondary", True)
        self.back_button.setAccessibleName("返回上一页")
        self.back_button.clicked.connect(self._go_back)
        page_layout.addWidget(self.back_button, 0, Qt.AlignmentFlag.AlignLeft)
        page_layout.addWidget(self.stack, 1)
        layout.addWidget(self.navigation)
        layout.addWidget(page_host, 1)
        shell_layout.addWidget(body, 1)
        self.setCentralWidget(root)
        self.size_grip = QSizeGrip(root)
        self.size_grip.setObjectName("windowSizeGrip")
        self.size_grip.resize(18, 18)
        self.navigation.page_selected.connect(self.navigate)
        self.history_page.result_requested.connect(self._open_history_result)
        self.workbench_page.module_selected.connect(self._open_module)
        self.module_task_page.task_requested.connect(self._start_task)
        self.module_task_page.configured_task_requested.connect(
            self._start_configured_task
        )
        self.module_task_page.ai_report_requested.connect(self._open_moisture_ai_report)
        self.module_task_page.governance_requested.connect(self._open_moisture_governance)
        self.after_sales_ai_setup_page.setup_completed.connect(
            self._continue_after_sales_setup
        )
        self.after_sales_ai_setup_page.action_failed.connect(
            lambda message: self._show_failure("售后 AI 接入", message)
        )
        self.moisture_governance_page.action_failed.connect(
            lambda message: self._show_failure("水分经验与规则管理", message)
        )
        self.moisture_ai_report_page.task_requested.connect(self._start_moisture_ai_report)
        self.moisture_ai_report_page.action_failed.connect(
            lambda message: self._show_failure("AI汇总报告", message)
        )
        self.task_progress_page.cancel_requested.connect(self._cancel_task)
        self.confirmations_page.submitted.connect(self._submit_confirmation)
        self.confirmations_page.job_selected.connect(self._select_confirmation_job)
        self.result_center_page.output_files.open_failed.connect(
            lambda message: self._show_failure("输出文件不可用", message)
        )
        self.settings_page.action_failed.connect(
            lambda message: self._show_failure("设置操作失败", message)
        )
        self.settings_page.settings_saved.connect(context.reload_ai_configuration)
        self.update_controller = UpdateController(self, context)
        self.settings_page.check_updates_requested.connect(
            self.update_controller.check_manually
        )
        self.update_controller.status_changed.connect(
            self.settings_page.set_update_status
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
        context.task_service.publication_warning.connect(
            lambda _job_id, message: self._show_failure("成果目录复制提醒", message)
        )
        for job_id, result in context.task_service.pending_confirmations():
            self._confirmation_job_ids.add(job_id)
            self.confirmations_page.load(job_id, result.confirmations)
        self._show_widget(
            self.workbench_page,
            nav_page=PageId.WORKBENCH,
            record_history=False,
        )

    def schedule_automatic_update_check(self) -> None:
        if not getattr(sys, "frozen", False) and os.environ.get(
            "BAMBOO_ENABLE_SOURCE_UPDATE_CHECK"
        ) != "1":
            return
        QTimer.singleShot(1500, self.update_controller.check_automatically)

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

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._enable_native_rounded_corners()

    def _enable_native_rounded_corners(self) -> bool:
        """Ask Windows DWM for antialiased corners without a jagged bitmap mask."""
        if sys.platform != "win32":
            return False
        try:
            preference = ctypes.c_int(2)  # DWMWCP_ROUND
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                int(self.winId()),
                33,  # DWMWA_WINDOW_CORNER_PREFERENCE
                ctypes.byref(preference),
                ctypes.sizeof(preference),
            )
        except (AttributeError, OSError):
            return False
        return result == 0

    @staticmethod
    def _placeholder(page_id: PageId) -> QWidget:
        page = QWidget()
        page.setObjectName(f"page-{page_id.value}")
        return page

    def navigate(self, page_id: PageId) -> None:
        if page_id is PageId.HISTORY:
            self.history_page.refresh()
        self._show_widget(self.pages[page_id], nav_page=page_id)

    def _show_widget(
        self,
        widget: QWidget,
        *,
        nav_page: PageId | None = None,
        record_history: bool = True,
    ) -> None:
        current = self.stack.currentWidget()
        if record_history and current is not None and current is not widget:
            entry = (current, self._current_nav_page)
            if not self._navigation_history or self._navigation_history[-1] != entry:
                self._navigation_history.append(entry)
        if nav_page is not None:
            self._current_nav_page = nav_page
        self.stack.setCurrentWidget(widget)
        self.navigation.set_current_page(self._current_nav_page)
        self.back_button.setVisible(widget is not self.workbench_page)

    def _go_back(self) -> None:
        while self._navigation_history:
            widget, nav_page = self._navigation_history.pop()
            if widget is self.stack.currentWidget():
                continue
            self._show_widget(widget, nav_page=nav_page, record_history=False)
            return
        self._show_widget(
            self.workbench_page,
            nav_page=PageId.WORKBENCH,
            record_history=False,
        )

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
        policy = module.manifest.framework_ai
        if (
            module_id is ModuleId.AFTER_SALES
            and policy is not None
            and policy.required
        ):
            self._after_sales_ai_ready = False
            self.after_sales_ai_setup_page.activate()
            self._show_widget(
                self.after_sales_ai_setup_page,
                nav_page=PageId.WORKBENCH,
            )
            return
        self._show_module_task(module_id, module)

    def _show_module_task(self, module_id: object, module: object) -> None:
        manifest = module.manifest
        self.module_task_page.set_module(
            module_id,
            manifest.module_name,
            manifest.supported_extensions,
            ai_report_available="ai_report" in manifest.capabilities,
            incremental_available=manifest.supports_incremental,
            governance_available=bool(
                manifest.management_contract
                and {"experience_management", "rule_management"}
                <= set(manifest.capabilities)
            ),
            framework_ai_required=bool(manifest.framework_ai and manifest.framework_ai.required),
        )
        self._show_widget(self.module_task_page, nav_page=PageId.WORKBENCH)

    def _continue_after_sales_setup(self) -> None:
        try:
            module = self.context.registry.get(ModuleId.AFTER_SALES)
        except KeyError as error:
            self._show_failure("模块不可用", str(error))
            return
        self._after_sales_ai_ready = True
        self._show_module_task(ModuleId.AFTER_SALES, module)

    def _start_task(self, module_id: object, files: list) -> None:
        self._start_task_with_config(module_id, files, None)

    def _start_configured_task(
        self,
        module_id: object,
        files: list,
        module_config: object,
    ) -> None:
        if not isinstance(module_config, dict):
            self._show_failure("任务创建失败", "模块任务配置无效")
            return
        self._start_task_with_config(module_id, files, module_config)

    def _start_task_with_config(
        self,
        module_id: object,
        files: list,
        module_config: dict[str, object] | None,
    ) -> None:
        self._starting_task = True
        self._start_failure_job_id = None
        try:
            job_id = self.context.task_service.create_and_start(
                module_id,
                files,
                module_config=module_config,
                ai_consent_granted=(
                    module_id is ModuleId.AFTER_SALES
                    and self._after_sales_ai_ready
                    and self.module_task_page.ai_consent.isChecked()
                ),
            )
        except Exception as error:
            self._show_failure("任务创建失败", str(error))
            return
        finally:
            self._starting_task = False
        if self._start_failure_job_id == job_id:
            return
        self._foreground_job_id = job_id
        if module_id is ModuleId.AFTER_SALES:
            self._after_sales_ai_ready = False
        self.task_progress_page.bind(job_id)
        self._show_widget(self.task_progress_page)

    def _open_moisture_ai_report(self, module_id: object) -> None:
        if getattr(module_id, "value", module_id) != "moisture":
            self._show_failure("功能不可用", "AI汇总报告入口当前只属于竹丝水分模块")
            return
        try:
            module = self.context.registry.get(ModuleId.MOISTURE)
        except KeyError:
            self._show_failure("功能不可用", "竹丝水分模块尚未安装")
            return
        if "ai_report" not in module.manifest.capabilities:
            self._show_failure("功能不可用", "当前竹丝水分模块版本尚未提供独立 AI 汇总报告")
            return
        self.moisture_ai_report_page.activate()
        self._show_widget(
            self.moisture_ai_report_page,
            nav_page=PageId.WORKBENCH,
        )

    def _open_moisture_governance(self, module_id: object) -> None:
        if module_id is not ModuleId.MOISTURE:
            self._show_failure("功能不可用", "经验与规则管理当前只属于竹丝水分模块")
            return
        try:
            module = self.context.registry.get(ModuleId.MOISTURE)
        except KeyError:
            self._show_failure("功能不可用", "竹丝水分模块尚未安装")
            return
        if not module.manifest.management_contract:
            self._show_failure("功能不可用", "当前水分模块尚未提供版本化管理合同")
            return
        self.moisture_governance_page.activate()
        self._show_widget(
            self.moisture_governance_page,
            nav_page=PageId.WORKBENCH,
        )

    def _start_moisture_ai_report(
        self,
        current_summary: Path,
        module_config: dict[str, object],
    ) -> None:
        self._starting_task = True
        self._start_failure_job_id = None
        try:
            job_id = self.context.task_service.create_and_start(
                ModuleId.MOISTURE,
                [current_summary],
                module_config=module_config,
            )
        except Exception as error:
            self._show_failure("AI汇总报告任务创建失败", str(error))
            return
        finally:
            self._starting_task = False
        if self._start_failure_job_id == job_id:
            return
        self._foreground_job_id = job_id
        self.task_progress_page.bind(job_id)
        self._show_widget(self.task_progress_page)

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
            self._show_widget(self.confirmations_page, nav_page=PageId.CONFIRMATIONS)

    def _select_confirmation_job(self, job_id: str) -> None:
        self._foreground_job_id = job_id
        self._show_widget(self.confirmations_page, nav_page=PageId.CONFIRMATIONS)

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
        self._show_widget(self.task_progress_page)

    def _on_finished(self, result: ModuleResult) -> None:
        result = normalized_result(result)
        self._clear_confirmation(result.job_id)
        if self._foreground_job_id != result.job_id:
            self.history_page.refresh()
            return
        if self.task_progress_page.current_job_id == result.job_id:
            self.task_progress_page.current_job_id = ""
            self.task_progress_page.cancel_button.setEnabled(False)
        self.result_center_page.show_result(result)
        self._show_widget(self.result_center_page)
        if result.status in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            self._show_failure("任务未完成", "；".join(result.errors) or result.status.value)
        self._foreground_job_id = None

    def _open_history_result(self, job_id: str) -> None:
        try:
            task = self.context.task_repository.get(job_id)
            if task["status"] not in {"success", "partial_success"}:
                return
            task_dir = self.context.paths.tasks / job_id
            result_path = resolve_contained_file(
                Path(str(task["result_path"])),
                task_dir,
                "历史任务结果",
                reject_link=True,
            )
            result = ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            if result.job_id != job_id or result.module_id.value != task["module_id"]:
                raise ValueError("历史任务结果与任务记录不匹配")
        except (KeyError, OSError, UnicodeError, ValueError) as error:
            self._show_failure("无法打开历史结果", str(error))
            return
        self.result_center_page.show_result(self._result_with_stored_outputs(result))
        self._show_widget(self.result_center_page, nav_page=PageId.HISTORY)

    def _historical_status(self, task: dict[str, object]) -> str:
        persisted = str(task["status"])
        if persisted not in {"success", "partial_success"}:
            return persisted
        try:
            job_id = str(task["job_id"])
            task_dir = self.context.paths.tasks / job_id
            result_path = resolve_contained_file(
                Path(str(task["result_path"])),
                task_dir,
                "历史任务结果",
                reject_link=True,
            )
            result = ModuleResult.model_validate_json(result_path.read_text(encoding="utf-8"))
            if result.job_id != job_id or result.module_id.value != task["module_id"]:
                return persisted
            return normalized_result(result).status.value
        except (KeyError, OSError, UnicodeError, ValueError, TypeError):
            return persisted

    def _result_with_stored_outputs(self, result: ModuleResult) -> ModuleResult:
        result = normalized_result(result)
        stored = self.context.task_repository.list_outputs(result.job_id)
        if len(stored) != len(result.outputs):
            return result
        outputs = [
            artifact.model_copy(update={"path": str(record["path"])})
            for artifact, record in zip(result.outputs, stored, strict=True)
        ]
        return result.model_copy(update={"outputs": outputs})

    def _on_failed(self, job_id: str, message: str) -> None:
        if self._starting_task:
            self._start_failure_job_id = job_id
        if self._finalizing_job_id == job_id:
            self._finalize_failed = True
        was_confirmation = job_id in self._confirmation_job_ids
        self._clear_confirmation(job_id)
        if self._foreground_job_id == job_id:
            target = self.confirmations_page if was_confirmation else self.module_task_page
            self._show_widget(target)
            self.task_progress_page.current_job_id = ""
            self.task_progress_page.cancel_button.setEnabled(False)
            self.task_progress_page.message_label.setText("任务执行失败")
            self._foreground_job_id = None
        self._show_failure("任务未完成", f"{self._task_display_name(job_id)}：{message}")

    def _on_orchestration_error(self, job_id: str, message: str) -> None:
        if self._starting_task:
            self._start_failure_job_id = job_id
        if self._finalizing_job_id == job_id:
            self._finalize_failed = True
        was_confirmation = job_id in self._confirmation_job_ids
        self._clear_confirmation(job_id)
        if self._foreground_job_id == job_id:
            target = self.confirmations_page if was_confirmation else self.module_task_page
            self._show_widget(target)
            self.task_progress_page.current_job_id = ""
            self.task_progress_page.cancel_button.setEnabled(False)
            self.task_progress_page.message_label.setText("任务协调错误")
            self._foreground_job_id = None
        self._show_failure("任务协调错误", f"{self._task_display_name(job_id)}：{message}")

    def _task_display_name(self, job_id: str) -> str:
        try:
            return f"任务 {self.context.task_repository.get_number(job_id)}"
        except KeyError:
            return "当前任务"

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
