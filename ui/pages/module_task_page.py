from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.file_drop_zone import FileDropZone


class ModuleTaskPage(QWidget):
    task_requested = Signal(object, list)
    configured_task_requested = Signal(object, list, object)
    ai_report_requested = Signal(object)
    governance_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-module-task")
        self.module_id: object | None = None
        self.files: list[Path] = []
        self.supported_extensions: set[str] = set()
        self.base_summary: Path | None = None
        self.incremental_available = False
        self.framework_ai_required = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        self.title = QLabel("创建任务")
        self.title.setProperty("pageTitle", True)
        self.subtitle = QLabel("导入原始文件后，由对应模块按既定规则生成表格、图表与分析结果。")
        self.subtitle.setProperty("subtle", True)
        self.file_drop_zone = FileDropZone()
        self.file_drop_zone.files_dropped.connect(self.add_files)
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_list.setAccessibleName("待处理文件列表")
        self.file_list.itemSelectionChanged.connect(self._update_buttons)
        self.intake_feedback = QLabel("请选择或拖放待处理文件")
        self.intake_feedback.setAccessibleName("文件接收状态")

        self.operation_form = QFormLayout()
        self.operation_combo = QComboBox()
        self.operation_combo.setAccessibleName("水分汇总方式")
        self.operation_combo.addItem("创建新的水分汇总表", "summary")
        self.operation_combo.addItem("在历史标准汇总表上追加", "append_summary")
        self.operation_combo.currentIndexChanged.connect(self._operation_changed)
        self.operation_form.addRow("处理方式", self.operation_combo)
        self.base_summary_row = QWidget()
        base_layout = QHBoxLayout(self.base_summary_row)
        base_layout.setContentsMargins(0, 0, 0, 0)
        base_layout.setSpacing(8)
        self.base_summary_edit = QLineEdit()
        self.base_summary_edit.setReadOnly(True)
        self.base_summary_edit.setPlaceholderText("请选择一份由水分模块生成的标准汇总表")
        self.base_summary_edit.setAccessibleName("历史标准水分汇总表")
        self.base_summary_button = QPushButton("选择历史汇总表…")
        self.base_summary_button.setProperty("secondary", True)
        self.base_summary_button.clicked.connect(self._pick_base_summary)
        base_layout.addWidget(self.base_summary_edit, 1)
        base_layout.addWidget(self.base_summary_button)
        self.operation_form.addRow("历史汇总表", self.base_summary_row)

        picker_row = QHBoxLayout()
        self.add_files_button = QPushButton("添加文件")
        self.add_files_button.setAccessibleName("添加文件")
        self.add_files_button.clicked.connect(self._pick_files)
        self.add_folder_button = QPushButton("添加文件夹")
        self.add_folder_button.setAccessibleName("添加文件夹")
        self.add_folder_button.clicked.connect(self._pick_folder)
        self.remove_button = QPushButton("移除选中")
        self.remove_button.setAccessibleName("移除选中文件")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("清空")
        self.clear_button.setAccessibleName("清空文件列表")
        self.clear_button.clicked.connect(self.clear_files)
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
        ):
            button.setProperty("secondary", True)
            picker_row.addWidget(button)
        picker_row.addStretch()

        self.run_button = QPushButton("创建任务")
        self.run_button.setProperty("primary", True)
        self.run_button.setAccessibleName("创建并运行任务")
        self.run_button.clicked.connect(self._run)
        self.ai_consent = QCheckBox(
            "我已查看数据外发说明，并授权本批次由框架 AI Provider 处理脱敏摘要"
        )
        self.ai_consent.setVisible(False)
        self.ai_consent.stateChanged.connect(self._update_buttons)
        self.ai_disclosure = QLabel(
            "框架只发送脱敏摘要和证据编号，不发送 Excel、原始文件名、客户身份或 API Key。"
            "AI 仅给出候选建议，售后费用、责任工厂和投诉类型仍须逐文件人工确认。"
        )
        self.ai_disclosure.setWordWrap(True)
        self.ai_disclosure.setProperty("subtle", True)
        self.ai_disclosure.setVisible(False)
        self.ai_report_button = QPushButton("打开 AI 汇总报告")
        self.ai_report_button.setProperty("secondary", True)
        self.ai_report_button.setAccessibleName("打开竹丝水分AI汇总报告")
        self.ai_report_button.clicked.connect(self._open_ai_report)
        self.ai_report_button.setVisible(False)
        self.governance_button = QPushButton("打开经验与规则管理")
        self.governance_button.setProperty("secondary", True)
        self.governance_button.clicked.connect(self._open_governance)
        self.governance_button.setVisible(False)
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 20)
        card_layout.setSpacing(12)
        card_layout.addLayout(self.operation_form)
        card_layout.addWidget(self.file_drop_zone)
        card_layout.addLayout(picker_row)
        card_layout.addWidget(self.file_list, 1)
        card_layout.addWidget(self.intake_feedback)
        card_layout.addWidget(self.ai_disclosure)
        card_layout.addWidget(self.ai_consent)
        card_layout.addWidget(self.run_button)
        card_layout.addWidget(self.ai_report_button)
        card_layout.addWidget(self.governance_button)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(card, 1)
        self._update_buttons()

    def set_module(
        self,
        module_id: object,
        title: str,
        supported_extensions: list[str] | None = None,
        *,
        ai_report_available: bool = False,
        incremental_available: bool = False,
        governance_available: bool = False,
        framework_ai_required: bool = False,
    ) -> None:
        self.module_id = module_id
        self.title.setText(title)
        extensions = supported_extensions or [".xlsx"]
        self.supported_extensions = {
            extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
            for extension in extensions
        }
        self.ai_report_button.setVisible(
            getattr(module_id, "value", module_id) == "moisture"
            and ai_report_available
        )
        self.governance_button.setVisible(
            getattr(module_id, "value", module_id) == "moisture" and governance_available
        )
        self.framework_ai_required = (
            getattr(module_id, "value", module_id) == "after_sales"
            and framework_ai_required
        )
        self.ai_consent.setChecked(False)
        self.ai_consent.setVisible(self.framework_ai_required)
        self.ai_disclosure.setVisible(self.framework_ai_required)
        self.run_button.setText(
            "开始智能分析并进入人工复核"
            if self.framework_ai_required
            else "创建任务"
        )
        is_moisture = getattr(module_id, "value", module_id) == "moisture"
        self.incremental_available = is_moisture and incremental_available
        self.operation_combo.setVisible(is_moisture and incremental_available)
        label = self.operation_form.labelForField(self.operation_combo)
        if label is not None:
            label.setVisible(is_moisture and incremental_available)
        self.operation_combo.setCurrentIndex(0)
        self.base_summary = None
        self.base_summary_edit.clear()
        self._operation_changed()
        self.clear_files()

    def add_files(self, paths: list[Path]) -> None:
        added = 0
        ignored = 0
        for candidate in paths:
            path = Path(candidate)
            try:
                valid = path.is_file() and path.suffix.casefold() in self.supported_extensions
                resolved = path.resolve(strict=True) if valid else None
            except OSError:
                resolved = None
            if resolved is None:
                ignored += 1
                continue
            if resolved in self.files:
                continue
            self.files.append(resolved)
            self.file_list.addItem(str(resolved))
            added += 1
        details = [f"已添加 {added} 个文件"]
        if ignored:
            details.append(f"已忽略 {ignored} 个不支持或无效的文件")
        self.intake_feedback.setText("；".join(details))
        self._update_buttons()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.file_list.selectedIndexes()}, reverse=True)
        for row in rows:
            self.file_list.takeItem(row)
            self.files.pop(row)
        if rows:
            self.intake_feedback.setText(f"已移除 {len(rows)} 个文件")
        self._update_buttons()

    def clear_files(self) -> None:
        self.files.clear()
        self.file_list.clear()
        self.intake_feedback.setText("请选择或拖放待处理文件")
        self._update_buttons()

    def _pick_base_summary(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "选择历史标准水分汇总表",
            "",
            "Excel 工作簿 (*.xlsx)",
        )
        if not selected:
            return
        try:
            candidate = Path(selected).resolve(strict=True)
        except OSError:
            self.intake_feedback.setText("选择的历史汇总表不可用")
            return
        if not candidate.is_file() or candidate.suffix.casefold() != ".xlsx":
            self.intake_feedback.setText("历史汇总表必须是有效的 .xlsx 文件")
            return
        self.base_summary = candidate
        self.base_summary_edit.setText(str(candidate))
        self._update_buttons()

    def _operation_changed(self) -> None:
        append_mode = self.incremental_available and (
            self.operation_combo.currentData() == "append_summary"
        )
        self.base_summary_row.setVisible(append_mode)
        label = self.operation_form.labelForField(self.base_summary_row)
        if label is not None:
            label.setVisible(append_mode)
        self.file_drop_zone.setAccessibleDescription(
            "拖放需要追加的新原始水分Excel文件"
            if append_mode
            else "拖放需要处理的业务文件"
        )
        self._update_buttons()

    def _pick_files(self) -> None:
        filters = " ".join(f"*{extension}" for extension in sorted(self.supported_extensions))
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "选择待处理文件",
            "",
            f"支持的文件 ({filters})" if filters else "所有文件 (*)",
        )
        if selected:
            self.add_files([Path(path) for path in selected])

    def _pick_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择待处理文件夹")
        if not selected:
            return
        folder = Path(selected)
        try:
            candidates = sorted(path for path in folder.rglob("*") if path.is_file())
        except OSError:
            candidates = []
        self.add_files(candidates)

    def _update_buttons(self) -> None:
        append_mode = self.incremental_available and (
            self.operation_combo.currentData() == "append_summary"
        )
        ready = bool(self.files) and (not append_mode or self.base_summary is not None)
        if self.framework_ai_required:
            ready = ready and self.ai_consent.isChecked()
        self.run_button.setEnabled(self.module_id is not None and ready)
        self.remove_button.setEnabled(bool(self.file_list.selectedItems()))
        self.clear_button.setEnabled(bool(self.files))

    def _run(self) -> None:
        if self.module_id is None or not self.files:
            return
        append_mode = self.incremental_available and (
            self.operation_combo.currentData() == "append_summary"
        )
        if not append_mode:
            self.task_requested.emit(self.module_id, list(self.files))
            return
        if self.base_summary is None:
            self.intake_feedback.setText("请先选择一份历史标准汇总表")
            return
        if self.base_summary in self.files:
            self.intake_feedback.setText("历史汇总表不能同时作为新原始数据")
            return
        inputs = [self.base_summary, *self.files]
        roles = [{"role": "base_summary", "input_index": 0}]
        roles.extend(
            {"role": "new_raw", "input_index": index}
            for index in range(1, len(inputs))
        )
        self.configured_task_requested.emit(
            self.module_id,
            inputs,
            {
                "schema_version": "1.0",
                "operation": "append_summary",
                "inputs": roles,
            },
        )

    def _open_ai_report(self) -> None:
        if self.module_id is not None:
            self.ai_report_requested.emit(self.module_id)

    def _open_governance(self) -> None:
        if self.module_id is not None:
            self.governance_requested.emit(self.module_id)
