from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.platform.paths import AppPaths
from core.storage.settings import SettingsStore


class SettingsPage(QWidget):
    action_failed = Signal(str)

    def __init__(self, settings: SettingsStore, paths: AppPaths) -> None:
        super().__init__()
        self.settings = settings
        self.paths = paths
        self.setObjectName("page-settings")
        self.setAccessibleName("系统设置")

        layout = QVBoxLayout(self)
        title = QLabel("系统设置")
        title.setProperty("heading", True)
        form = QFormLayout()
        self.output_dir_edit = QLineEdit(settings.get("output_dir", "") or "")
        self.output_dir_edit.setAccessibleName("输出目录")
        form.addRow("输出目录", self.output_dir_edit)
        self.save_button = QPushButton("保存设置")
        self.save_button.setAccessibleName("保存系统设置")
        self.save_button.clicked.connect(self.save)
        self.open_logs_button = QPushButton("打开日志目录")
        self.open_logs_button.setAccessibleName("打开应用日志目录")
        self.open_logs_button.clicked.connect(self.open_log_directory)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.save_button)
        layout.addWidget(self.open_logs_button)
        layout.addStretch()

    def save(self) -> None:
        self.settings.set("output_dir", self.output_dir_edit.text())

    def open_log_directory(self) -> None:
        try:
            self.paths.logs.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.logs.resolve())))
        except Exception as error:
            self.action_failed.emit(str(error))
            return
        if not opened:
            self.action_failed.emit("系统未能打开日志目录")
