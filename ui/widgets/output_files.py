from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.contracts.result import OutputArtifact


class OutputFilesWidget(QWidget):
    open_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self.buttons: list[QPushButton] = []

    def set_outputs(self, outputs: list[OutputArtifact]) -> None:
        self._clear()
        for artifact in outputs:
            path = self._existing_file(artifact.path)
            if path is None:
                continue
            button = QPushButton(f"打开{artifact.label}")
            button.setAccessibleName(f"打开{artifact.label}")
            button.setAccessibleDescription(str(path))
            raw_path = Path(artifact.path)
            button.clicked.connect(lambda checked=False, target=raw_path: self._open_output(target))
            self.buttons.append(button)
            self._layout.addWidget(button)
        if not self.buttons:
            self._layout.addWidget(QLabel("没有可打开的输出文件"))
        self._layout.addStretch()

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.buttons.clear()

    @staticmethod
    def _existing_file(raw_path: str) -> Path | None:
        path = Path(raw_path)
        try:
            if path.is_symlink() or not path.is_file():
                return None
            return path.resolve(strict=True)
        except (OSError, RuntimeError):
            return None

    def _open_output(self, path: Path) -> None:
        resolved = self._existing_file(str(path))
        if resolved is None:
            self.open_failed.emit("输出文件不可用，可能已移动、删除或被链接替换")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved))):
            self.open_failed.emit("系统未能打开输出文件")
