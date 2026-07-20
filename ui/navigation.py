from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.page_ids import PageId


class Navigation(QWidget):
    page_selected = Signal(object)

    def __init__(self, logo_path: Path) -> None:
        super().__init__()
        self.setObjectName("navigation")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAccessibleName("主导航")
        self.setAccessibleDescription("竹简工作台的页面导航")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 24, 18, 22)
        layout.setSpacing(8)

        brand = QWidget()
        brand.setObjectName("navigationBrand")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(10)
        self.logo = QLabel()
        self.logo.setObjectName("teamLogo")
        self.logo.setAccessibleName("湖南大学智创未来团队标志")
        self.logo.setAccessibleDescription("绿色圆形湖南大学智创未来团队标志")
        self.logo.setPixmap(QPixmap(str(logo_path)))
        self.logo.setScaledContents(True)
        self.logo.setFixedSize(48, 48)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        self.team_name = QLabel("湖南大学\n智创未来团队")
        self.team_name.setObjectName("navigationTeamName")
        self.team_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.team_english = QLabel("HNU · INNOVATION\nFOR BAMBOO")
        self.team_english.setObjectName("navigationTeamEnglish")
        brand_text.addWidget(self.team_name)
        brand_text.addWidget(self.team_english)
        brand_layout.addWidget(self.logo)
        brand_layout.addLayout(brand_text, 1)
        layout.addWidget(brand)
        layout.addSpacing(22)

        labels = {
            PageId.WORKBENCH: ("⌂", "工作台"),
            PageId.HISTORY: ("☷", "任务历史"),
            PageId.CONFIRMATIONS: ("✓", "待确认"),
            PageId.KNOWLEDGE: ("◇", "知识库"),
            PageId.SETTINGS: ("⚙", "系统设置"),
        }
        self.buttons: dict[PageId, QPushButton] = {}
        for page_id, (icon, label) in labels.items():
            button = QPushButton(f"{icon}   {label}")
            button.setObjectName(f"navigation-{page_id.value}")
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, value=page_id: self.page_selected.emit(value)
            )
            self.buttons[page_id] = button
            layout.addWidget(button)
        layout.addStretch()
        self.footer = QLabel("专业技术未忘实践\n本地运行 · 数据可追溯")
        self.footer.setObjectName("navigationFooter")
        layout.addWidget(self.footer)

    def set_current_page(self, page_id: PageId) -> None:
        for candidate, button in self.buttons.items():
            button.setChecked(candidate is page_id)
