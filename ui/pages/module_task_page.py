from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.file_drop_zone import FileDropZone


class ModuleTaskPage(QWidget):
    task_requested = Signal(object, list, object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-module-task")
        self.module_id: object | None = None
        self.files: list[Path] = []
        self.supported_extensions: set[str] = set()

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
        self.year_label = QLabel("历史数据年份（仅当文件内没有完整年份时使用）")
        self.default_year = QSpinBox()
        self.default_year.setRange(0, 2100)
        self.default_year.setSpecialValueText("未指定")
        self.default_year.setAccessibleName("历史数据默认年份")
        self.default_year.setToolTip("请输入业务文件所属年份；不会使用当前年份或文件时间猜测。")

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
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 20)
        card_layout.setSpacing(12)
        card_layout.addWidget(self.file_drop_zone)
        card_layout.addLayout(picker_row)
        card_layout.addWidget(self.file_list, 1)
        card_layout.addWidget(self.intake_feedback)
        card_layout.addWidget(self.year_label)
        card_layout.addWidget(self.default_year)
        card_layout.addWidget(self.run_button)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addWidget(card, 1)
        self._update_buttons()

    def set_module(
        self,
        module_id: object,
        title: str,
        supported_extensions: list[str] | None = None,
    ) -> None:
        self.module_id = module_id
        self.title.setText(title)
        extensions = supported_extensions or [".xlsx"]
        self.supported_extensions = {
            extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
            for extension in extensions
        }
        is_moisture = getattr(module_id, "value", module_id) == "moisture"
        self.year_label.setVisible(is_moisture)
        self.default_year.setVisible(is_moisture)
        self.default_year.setValue(0)
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
        self.run_button.setEnabled(self.module_id is not None and bool(self.files))
        self.remove_button.setEnabled(bool(self.file_list.selectedItems()))
        self.clear_button.setEnabled(bool(self.files))

    def _run(self) -> None:
        if self.module_id is not None and self.files:
            module_config = None
            if (
                getattr(self.module_id, "value", self.module_id) == "moisture"
                and self.default_year.value()
            ):
                module_config = {"default_year": self.default_year.value()}
            self.task_requested.emit(self.module_id, list(self.files), module_config)
