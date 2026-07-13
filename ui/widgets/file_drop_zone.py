from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class FileDropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("文件拖放区")
        self.setAccessibleDescription("将待处理文件拖放到这里")
        layout = QVBoxLayout(self)
        label = QLabel("拖放文件到此处")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def dragEnterEvent(self, event: object) -> None:
        mime_data = event.mimeData()
        if mime_data.hasUrls() and any(url.isLocalFile() for url in mime_data.urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: object) -> None:
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if not paths:
            event.ignore()
            return
        self.files_dropped.emit(paths)
        event.acceptProposedAction()
