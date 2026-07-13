from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.contracts.result import OutputArtifact


class OutputFilesWidget(QWidget):
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
            button.clicked.connect(lambda checked=False, target=path: self._open_output(target))
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
            if not path.is_file():
                return None
            return path.resolve(strict=True)
        except OSError:
            return None

    @staticmethod
    def _open_output(path: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
