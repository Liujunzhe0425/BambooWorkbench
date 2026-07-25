from __future__ import annotations

import json
from collections import deque

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.contracts.enums import ModuleId
from core.modules.management_service import ModuleManagementService

_EXPERIENCE_LISTS = (
    ("经验草稿", "list_experience_drafts"),
    ("当前已批准经验", "list_experience_approved"),
    ("经验历史", "list_experience_history"),
)
_RULE_LISTS = (
    ("规则草稿", "list_rule_drafts"),
    ("当前有效规则", "list_current_rules"),
    ("规则历史", "list_rule_history"),
)
_OPERATIONS = (
    "show_experience",
    "validate_experience_draft",
    "create_experience_draft",
    "update_experience_draft",
    "publish_experience",
    "retire_experience",
    "copy_experience_history_to_draft",
    "get_active_rule_identity",
    "show_rule_package",
    "validate_rule_draft",
    "preview_rule_draft",
    "create_rule_draft",
    "update_rule_draft",
    "publish_rule",
    "retire_current_rule",
    "restore_rule_version",
    "copy_rule_history_to_draft",
)


class MoistureGovernancePage(QWidget):
    action_failed = Signal(str)

    def __init__(self, management: ModuleManagementService) -> None:
        super().__init__()
        self.management = management
        self._pending: deque[str] = deque()
        self._active_operation: str | None = None
        self._lists: dict[str, QListWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        title = QLabel("水分经验与规则管理")
        title.setProperty("pageTitle", True)
        note = QLabel(
            "所有写操作均通过模块公开管理进程执行；框架不导入模块内部服务。"
            "发布和停用前请核对版本与 SHA-256。"
        )
        note.setWordWrap(True)
        note.setProperty("subtle", True)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._three_pane(_EXPERIENCE_LISTS), "经验管理")
        self.tabs.addTab(self._three_pane(_RULE_LISTS), "规则管理")

        action_card = QFrame()
        action_card.setProperty("card", True)
        action_layout = QVBoxLayout(action_card)
        form = QFormLayout()
        self.operation_combo = QComboBox()
        for operation in _OPERATIONS:
            self.operation_combo.addItem(operation, operation)
        self.parameters_edit = QPlainTextEdit("{}")
        self.parameters_edit.setPlaceholderText("输入当前操作的 parameters JSON")
        self.parameters_edit.setMaximumHeight(160)
        form.addRow("公开操作", self.operation_combo)
        form.addRow("parameters", self.parameters_edit)
        self.run_button = QPushButton("执行公开操作")
        self.run_button.setProperty("primary", True)
        self.run_button.clicked.connect(self._run_selected)
        self.response_view = QPlainTextEdit()
        self.response_view.setReadOnly(True)
        self.response_view.setPlaceholderText("经模块 Schema 校验的响应会显示在这里")
        action_layout.addLayout(form)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.response_view)

        self.refresh_button = QPushButton("刷新六个栏位")
        self.refresh_button.setProperty("secondary", True)
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(action_card, 1)

        management.completed.connect(self._completed)
        management.failed.connect(self._failed)
        management.cancelled.connect(self._cancelled)

    def activate(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        if self.management.is_running:
            return
        self._pending = deque(operation for _title, operation in (*_EXPERIENCE_LISTS, *_RULE_LISTS))
        self._run_next()

    def _three_pane(self, definitions: tuple[tuple[str, str], ...]) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        splitter = QSplitter()
        for title, operation in definitions:
            pane = QFrame()
            pane.setProperty("card", True)
            pane_layout = QVBoxLayout(pane)
            pane_layout.addWidget(QLabel(title))
            listing = QListWidget()
            listing.setAccessibleName(title)
            pane_layout.addWidget(listing)
            self._lists[operation] = listing
            splitter.addWidget(pane)
        layout.addWidget(splitter)
        return page

    def _run_selected(self) -> None:
        try:
            parameters = json.loads(self.parameters_edit.toPlainText())
        except json.JSONDecodeError:
            self.action_failed.emit("parameters 必须是合法 JSON")
            return
        if not isinstance(parameters, dict):
            self.action_failed.emit("parameters 必须是 JSON 对象")
            return
        self._start(str(self.operation_combo.currentData()), parameters)

    def _start(self, operation: str, parameters: dict[str, object]) -> None:
        if self.management.is_running:
            self.action_failed.emit("已有水分管理操作正在执行")
            return
        try:
            self._active_operation = operation
            self.management.run_custom(ModuleId.MOISTURE, operation, parameters)
        except Exception as error:
            self._active_operation = None
            self.action_failed.emit(str(error))

    def _run_next(self) -> None:
        if not self._pending:
            return
        self._start(self._pending.popleft(), {})

    def _completed(self, operation: object, response: object) -> None:
        if str(operation) != self._active_operation or not isinstance(response, dict):
            return
        self._active_operation = None
        self.response_view.setPlainText(json.dumps(response, ensure_ascii=False, indent=2))
        listing = self._lists.get(str(operation))
        result = response.get("result")
        if listing is not None and isinstance(result, dict):
            items = result.get("experience_items", result.get("rule_items", []))
            listing.clear()
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        listing.addItem(self._item_label(item))
        self._run_next()

    def _failed(self, operation: object, message: str) -> None:
        if str(operation) != self._active_operation:
            return
        self._active_operation = None
        self.action_failed.emit(message)
        self._pending.clear()

    def _cancelled(self, operation: object) -> None:
        if str(operation) == self._active_operation:
            self._active_operation = None
            self._pending.clear()

    @staticmethod
    def _item_label(item: dict[str, object]) -> str:
        identity = item.get("experience_id", item.get("rule_version", "未知"))
        version = item.get("version", item.get("lifecycle", ""))
        digest = str(item.get("sha256", item.get("package_hash", "")))[:12]
        return " · ".join(str(value) for value in (identity, version, digest) if value)
