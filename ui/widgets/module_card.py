from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class ModuleCard(QFrame):
    activated = Signal(object)

    def __init__(
        self,
        module_id: object,
        title: str,
        registry: object,
        badge: str = "竹",
        description: str = "模块接口已预留，可接入后生成统一成果。",
    ) -> None:
        super().__init__()
        self.module_id = module_id
        self.setProperty("card", True)
        self.setProperty("moduleCard", True)
        self.setAccessibleName(f"{title}模块")
        self.setAccessibleDescription(f"打开{title}任务创建页面")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)
        self.badge_label = QLabel(badge)
        self.badge_label.setObjectName("moduleBadge")
        self.badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_label.setFixedSize(38, 38)
        self.title_label = QLabel(title)
        self.title_label.setProperty("section", True)
        self.description_label = QLabel(description)
        self.description_label.setProperty("subtle", True)
        self.description_label.setWordWrap(True)
        self.is_installed = self._is_installed(registry, module_id)
        self.state_label = QLabel(self._state_text(registry, module_id))
        self.state_label.setProperty("pill", True)
        self.open_button = QPushButton("打开模块" if self.is_installed else "暂未安装")
        self.open_button.setProperty("secondary", True)
        self.open_button.setAccessibleName(f"打开{title}")
        self.open_button.setEnabled(self.is_installed)
        self.open_button.clicked.connect(lambda checked=False: self.activated.emit(self.module_id))
        layout.addWidget(self.badge_label)
        layout.addWidget(self.title_label)
        layout.addWidget(self.description_label)
        layout.addStretch()
        layout.addWidget(self.state_label)
        layout.addWidget(self.open_button)

    @staticmethod
    def _state_text(registry: object, module_id: object) -> str:
        try:
            module = registry.get(module_id)
        except KeyError:
            return "暂未安装 · 等待接入"
        source = "模拟模块" if module.is_mock else "正式模块"
        health = {
            "healthy": "健康",
            "unhealthy": "异常",
            "unknown": "状态未知",
        }.get(module.health, "状态未知")
        return f"已安装 · {source} · {health}"

    @staticmethod
    def _is_installed(registry: object, module_id: object) -> bool:
        try:
            registry.get(module_id)
        except KeyError:
            return False
        return True
