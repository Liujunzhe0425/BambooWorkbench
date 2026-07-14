from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class FileDropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("fileDropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName("文件拖放区")
        self.setAccessibleDescription("将待处理文件拖放到这里")
        self.setMinimumHeight(138)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(5)
        icon = QLabel("⇩")
        icon.setProperty("dropIcon", True)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel("拖放文件到此处")
        label.setProperty("section", True)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("也可以使用下方按钮选择文件或整个文件夹")
        hint.setProperty("subtle", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addWidget(hint)

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
