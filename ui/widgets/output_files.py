import json
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.contracts.result import OutputArtifact


class OutputFilesWidget(QWidget):
    open_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self.buttons: list[QPushButton] = []
        self.text_viewers: list[QDialog] = []

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
            button.clicked.connect(
                lambda checked=False,
                target=raw_path,
                mime_type=artifact.mime_type,
                label=artifact.label: self._open_output(target, mime_type, label)
            )
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

    def _open_output(self, path: Path, mime_type: str = "", label: str = "") -> None:
        resolved = self._existing_file(str(path))
        if resolved is None:
            self.open_failed.emit("输出文件不可用，可能已移动、删除或被链接替换")
            return
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved))):
            return
        if self._is_text_artifact(resolved, mime_type):
            try:
                self._show_text_artifact(resolved, label)
                return
            except OSError as error:
                self.open_failed.emit(f"无法读取输出文件：{error}")
                return
        self.open_failed.emit("系统未能打开输出文件，且该文件不支持内置预览")

    @staticmethod
    def _is_text_artifact(path: Path, mime_type: str) -> bool:
        return mime_type.startswith("text/") or mime_type in {
            "application/json",
            "application/yaml",
        } or path.suffix.lower() in {
            ".md",
            ".json",
            ".txt",
            ".csv",
            ".log",
            ".yaml",
            ".yml",
        }

    def _show_text_artifact(self, path: Path, label: str) -> None:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        if path.suffix.lower() == ".json":
            with suppress(json.JSONDecodeError):
                content = json.dumps(json.loads(content), ensure_ascii=False, indent=2)
        viewer = QDialog(self)
        viewer.setWindowTitle(label or path.name)
        viewer.setModal(False)
        viewer.resize(860, 620)
        layout = QVBoxLayout(viewer)
        title = QLabel(f"{label or path.name} · {path.name}")
        title.setProperty("section", True)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(content)
        editor.setAccessibleName(f"{label or path.name}内容")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(viewer.close)
        layout.addWidget(title)
        layout.addWidget(editor, 1)
        layout.addWidget(buttons)
        self.text_viewers.append(viewer)
        viewer.finished.connect(
            lambda _result, dialog=viewer: self._remove_text_viewer(dialog)
        )
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def _remove_text_viewer(self, viewer: QDialog) -> None:
        if viewer in self.text_viewers:
            self.text_viewers.remove(viewer)
        viewer.deleteLater()
