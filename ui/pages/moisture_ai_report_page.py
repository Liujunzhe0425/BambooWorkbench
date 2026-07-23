from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.contracts.enums import ModuleId
from core.contracts.management import (
    ModuleManagementOperation,
    ModuleManagementResponse,
)
from core.modules.management_service import ModuleManagementService
from core.storage.settings import SettingsStore


class MoistureAIReportPage(QWidget):
    task_requested = Signal(object, object)
    action_failed = Signal(str)

    def __init__(
        self,
        management: ModuleManagementService,
        settings: SettingsStore | None = None,
    ) -> None:
        super().__init__()
        self.management = management
        self.settings = settings
        self.current_summary: Path | None = None
        self._refresh_queue: list[ModuleManagementOperation] = []
        self.setObjectName("page-moisture-ai-report")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(14)
        title = QLabel("竹丝水分 · AI汇总报告")
        title.setProperty("pageTitle", True)
        subtitle = QLabel(
            "主动选择当前汇总表和可选参考资料，生成独立 AI 辅助报告；"
            "不会修改原汇总表或替代人工质量结论。"
        )
        subtitle.setProperty("subtle", True)
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 20)
        card_layout.setSpacing(12)

        current_title = QLabel("1. 当前水分汇总表（必选）")
        current_title.setProperty("section", True)
        current_row = QHBoxLayout()
        self.current_label = QLabel("尚未选择")
        self.current_label.setProperty("subtle", True)
        self.current_label.setWordWrap(True)
        self.pick_current_button = QPushButton("选择汇总表")
        self.pick_current_button.setProperty("secondary", True)
        self.pick_current_button.clicked.connect(self._pick_current)
        current_row.addWidget(self.current_label, 1)
        current_row.addWidget(self.pick_current_button)
        card_layout.addWidget(current_title)
        card_layout.addLayout(current_row)

        selection_grid = QGridLayout()
        selection_grid.setHorizontalSpacing(16)
        history_host = self._selection_host("2. 历史汇总（可选）")
        experience_host = self._selection_host("3. 已批准经验（可选）")
        self.history_list = QListWidget()
        self.history_list.setAccessibleName("可选择的历史水分汇总")
        self.experience_list = QListWidget()
        self.experience_list.setAccessibleName("可选择的已批准水分经验")
        history_host.layout().addWidget(self.history_list, 1)
        experience_host.layout().addWidget(self.experience_list, 1)

        history_actions = QHBoxLayout()
        self.import_history_button = QPushButton("导入历史汇总")
        self.import_history_button.setProperty("secondary", True)
        self.import_history_button.clicked.connect(self._import_history)
        self.retire_history_button = QPushButton("停用选中历史")
        self.retire_history_button.setProperty("secondary", True)
        self.retire_history_button.clicked.connect(self._retire_history)
        history_actions.addWidget(self.import_history_button)
        history_actions.addWidget(self.retire_history_button)
        history_host.layout().addLayout(history_actions)

        self.refresh_button = QPushButton("刷新历史与经验")
        self.refresh_button.setProperty("secondary", True)
        self.refresh_button.clicked.connect(self.refresh_management_data)
        experience_host.layout().addWidget(self.refresh_button)
        selection_grid.addWidget(history_host, 0, 0)
        selection_grid.addWidget(experience_host, 0, 1)
        selection_grid.setColumnStretch(0, 1)
        selection_grid.setColumnStretch(1, 1)
        card_layout.addLayout(selection_grid)

        question_title = QLabel("4. 希望 AI 分析的问题（必填）")
        question_title.setProperty("section", True)
        self.question_edit = QPlainTextEdit()
        self.question_edit.setAccessibleName("AI汇总报告分析问题")
        self.question_edit.setPlaceholderText(
            "例如：请比较当前批次与所选历史数据的总体变化，并列出需要人工复核的批次。"
        )
        self.question_edit.setMaximumHeight(110)
        self.question_count = QLabel("0 / 2000")
        self.question_count.setProperty("caption", True)
        self.question_edit.textChanged.connect(self._update_question_count)
        card_layout.addWidget(question_title)
        card_layout.addWidget(self.question_edit)
        card_layout.addWidget(self.question_count)

        self.management_status = QLabel()
        self.management_status.setWordWrap(True)
        self.management_status.setProperty("subtle", True)
        self.prepare_button = QPushButton("校验并准备联网预览")
        self.prepare_button.setProperty("primary", True)
        self.prepare_button.clicked.connect(self._prepare)
        self.cancel_management_button = QPushButton("取消资料操作")
        self.cancel_management_button.setProperty("secondary", True)
        self.cancel_management_button.clicked.connect(self._cancel_management)
        self.cancel_management_button.setVisible(False)
        self.ai_status = QLabel()
        self.ai_status.setProperty("caption", True)
        self.ai_status.setWordWrap(True)
        note = QLabel(
            "下一步会先由模块生成限长、脱敏的发送内容；只有你在待确认页明确选择“允许”后，"
            "框架才会调用当前配置的 AI 服务。"
        )
        note.setWordWrap(True)
        note.setProperty("caption", True)
        card_layout.addWidget(self.management_status)
        card_layout.addWidget(self.ai_status)
        card_layout.addWidget(note)
        card_layout.addWidget(self.prepare_button)
        card_layout.addWidget(self.cancel_management_button)
        layout.addWidget(card, 1)

        management.progress.connect(self._management_progress)
        management.completed.connect(self._management_completed)
        management.failed.connect(self._management_failed)
        management.cancelled.connect(self._management_cancelled)
        self._set_management_availability()

    @staticmethod
    def _selection_host(title: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("softCard", True)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 14)
        label = QLabel(title)
        label.setProperty("section", True)
        layout.addWidget(label)
        return frame

    def activate(self) -> None:
        self._update_ai_status()
        self._set_management_availability()
        if self.management.is_available(ModuleId.MOISTURE):
            self.refresh_management_data()

    def refresh_management_data(self) -> None:
        if not self.management.is_available(ModuleId.MOISTURE):
            self._set_management_availability()
            return
        if self.management.is_running:
            return
        self._refresh_queue = [
            ModuleManagementOperation.LIST_HISTORY_SUMMARIES,
            ModuleManagementOperation.LIST_APPROVED_EXPERIENCES,
        ]
        self._run_next_refresh()

    def _run_next_refresh(self) -> None:
        if not self._refresh_queue:
            self.management_status.setText("历史资料与已批准经验目录已刷新。")
            self._set_management_buttons(True)
            return
        operation = self._refresh_queue.pop(0)
        self._set_management_buttons(False)
        try:
            self.management.run(ModuleId.MOISTURE, operation)
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            self._refresh_queue.clear()
            self._management_failed(operation, str(error))

    def _pick_current(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择当前水分汇总表",
            "",
            "Excel 汇总表 (*.xlsx)",
        )
        if not selected:
            return
        try:
            candidate = Path(selected).resolve(strict=True)
        except OSError as error:
            self.action_failed.emit(f"无法读取所选汇总表：{error}")
            return
        if candidate.suffix.casefold() != ".xlsx" or not candidate.is_file():
            self.action_failed.emit("当前汇总表必须是可读取的 .xlsx 文件")
            return
        self.current_summary = candidate
        self.current_label.setText(candidate.name)
        self.current_label.setToolTip(candidate.name)

    def _import_history(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "导入历史水分汇总表",
            "",
            "Excel 汇总表 (*.xlsx)",
        )
        if not selected:
            return
        try:
            self._set_management_buttons(False)
            self.management.run(
                ModuleId.MOISTURE,
                ModuleManagementOperation.IMPORT_HISTORY_SUMMARY,
                input_file=Path(selected),
            )
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            self._management_failed(
                ModuleManagementOperation.IMPORT_HISTORY_SUMMARY,
                str(error),
            )

    def _retire_history(self) -> None:
        item = self.history_list.currentItem()
        payload = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not isinstance(payload, dict) or not payload.get("history_id"):
            self.action_failed.emit("请先选中一条需要停用的历史汇总")
            return
        try:
            self._set_management_buttons(False)
            self.management.run(
                ModuleId.MOISTURE,
                ModuleManagementOperation.RETIRE_HISTORY_SUMMARY,
                history_id=str(payload["history_id"]),
            )
        except (KeyError, OSError, RuntimeError, ValueError) as error:
            self._management_failed(
                ModuleManagementOperation.RETIRE_HISTORY_SUMMARY,
                str(error),
            )

    def _management_progress(self, operation: object, event: object) -> None:
        message = getattr(event, "message", "正在处理模块资料")
        self.management_status.setText(str(message))

    def _management_completed(
        self,
        operation: ModuleManagementOperation,
        response: ModuleManagementResponse,
    ) -> None:
        if operation is ModuleManagementOperation.LIST_HISTORY_SUMMARIES:
            self._populate_history(response)
        elif operation is ModuleManagementOperation.LIST_APPROVED_EXPERIENCES:
            self._populate_experiences(response)
        elif operation in {
            ModuleManagementOperation.IMPORT_HISTORY_SUMMARY,
            ModuleManagementOperation.RETIRE_HISTORY_SUMMARY,
        }:
            self.management_status.setText(response.message or "模块资料操作已完成。")
            self.refresh_management_data()
            return
        if self._refresh_queue:
            self._run_next_refresh()
        else:
            self._set_management_buttons(True)

    def _management_failed(self, operation: object, message: str) -> None:
        self._refresh_queue.clear()
        self.management_status.setText(f"历史/经验资料暂不可用：{message}")
        self._set_management_buttons(
            self.management.is_available(ModuleId.MOISTURE)
        )

    def _management_cancelled(self, operation: object) -> None:
        self._refresh_queue.clear()
        self.management_status.setText("模块资料操作已取消。")
        self._set_management_buttons(True)

    def _cancel_management(self) -> None:
        if self.management.cancel():
            self.management_status.setText("正在取消资料操作……")
            self.cancel_management_button.setEnabled(False)

    def _populate_history(self, response: ModuleManagementResponse) -> None:
        self.history_list.clear()
        for record in response.history_items:
            if not record.active:
                continue
            date_range = ""
            if record.date_start or record.date_end:
                date_range = f" · {record.date_start or '?'} 至 {record.date_end or '?'}"
            item = QListWidgetItem(f"{record.display_name}{date_range}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, record.model_dump(mode="json"))
            self.history_list.addItem(item)

    def _populate_experiences(self, response: ModuleManagementResponse) -> None:
        self.experience_list.clear()
        for record in response.experience_items:
            item = QListWidgetItem(f"{record.title} · {record.version}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, record.model_dump(mode="json"))
            self.experience_list.addItem(item)

    def _prepare(self) -> None:
        if self.current_summary is None:
            self.action_failed.emit("请先选择当前水分汇总表")
            return
        question = self.question_edit.toPlainText().strip()
        if not 1 <= len(question) <= 2000:
            self.action_failed.emit("分析问题需要填写 1 至 2000 个字符")
            return
        history_ids = self._checked_values(self.history_list, "history_id")
        experiences = []
        for payload in self._checked_payloads(self.experience_list):
            experiences.append(
                {
                    "entry_id": str(payload["entry_id"]),
                    "version": str(payload["version"]),
                    "sha256": str(payload["sha256"]),
                }
            )
        config = {
            "schema_version": "1.0",
            "operation": "ai_report",
            "inputs": [{"role": "current_summary", "input_index": 0}],
            "history_ids": history_ids,
            "experience_selections": experiences,
            "question": question,
        }
        self.task_requested.emit(self.current_summary, config)

    @staticmethod
    def _checked_payloads(widget: QListWidget) -> list[dict[str, object]]:
        selected: list[dict[str, object]] = []
        for index in range(widget.count()):
            item = widget.item(index)
            if item.checkState() is not Qt.CheckState.Checked:
                continue
            payload = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(payload, dict):
                selected.append(payload)
        return selected

    @classmethod
    def _checked_values(cls, widget: QListWidget, key: str) -> list[str]:
        return [str(payload[key]) for payload in cls._checked_payloads(widget)]

    def _update_question_count(self) -> None:
        count = len(self.question_edit.toPlainText())
        self.question_count.setText(f"{count} / 2000")
        self.question_count.setProperty("warning", count > 2000)

    def _set_management_availability(self) -> None:
        available = self.management.is_available(ModuleId.MOISTURE)
        self._set_management_buttons(available)
        if available:
            self.management_status.setText("可选择本机历史汇总和模块已批准经验。")
        else:
            self.management_status.setText(
                "当前水分模块尚未安装历史/经验管理入口；本次仍可只使用当前汇总表生成 AI 报告。"
            )

    def _set_management_buttons(self, enabled: bool) -> None:
        idle = enabled and not self.management.is_running
        self.import_history_button.setEnabled(idle)
        self.retire_history_button.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.cancel_management_button.setVisible(self.management.is_running)
        self.cancel_management_button.setEnabled(self.management.is_running)

    def _update_ai_status(self) -> None:
        if self.settings is None:
            self.ai_status.setText("AI 服务状态将在联网授权页再次确认。")
            return
        provider = self.settings.get("ai_provider", "mock") or "mock"
        model = self.settings.get("ai_model", "mock-model") or "mock-model"
        enabled = self.settings.get("ai_network_enabled", "false") == "true"
        if provider == "mock":
            state = "离线模拟"
        elif enabled:
            state = "已启用联网（仍需逐次授权）"
        else:
            state = "未启用联网"
        self.ai_status.setText(f"当前 AI：{provider} / {model} · {state}")
