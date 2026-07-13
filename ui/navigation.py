from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from ui.page_ids import PageId


class Navigation(QWidget):
    page_selected = Signal(object)

    def __init__(self, logo_path: Path) -> None:
        super().__init__()
        self.setObjectName("navigation")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 24, 20, 24)
        layout.setSpacing(6)

        self.logo = QLabel("湖大智竹实践团队")
        self.logo.setObjectName("teamLogo")
        self.logo.setPixmap(QPixmap(str(logo_path)))
        self.logo.setScaledContents(True)
        self.logo.setFixedSize(150, 54)
        layout.addWidget(self.logo)
        layout.addSpacing(26)

        labels = {
            PageId.WORKBENCH: "工作台",
            PageId.HISTORY: "任务历史",
            PageId.CONFIRMATIONS: "待确认",
            PageId.KNOWLEDGE: "知识库",
            PageId.SETTINGS: "系统设置",
        }
        self.buttons: dict[PageId, QPushButton] = {}
        for page_id, label in labels.items():
            button = QPushButton(label)
            button.setObjectName(f"navigation-{page_id.value}")
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, value=page_id: self.page_selected.emit(value)
            )
            self.buttons[page_id] = button
            layout.addWidget(button)
        layout.addStretch()

    def set_current_page(self, page_id: PageId) -> None:
        for candidate, button in self.buttons.items():
            button.setChecked(candidate is page_id)
