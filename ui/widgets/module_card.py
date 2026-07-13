from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class ModuleCard(QWidget):
    activated = Signal(object)

    def __init__(self, module_id: object, title: str, registry: object) -> None:
        super().__init__()
        self.module_id = module_id
        self.setAccessibleName(f"{title}模块")
        self.setAccessibleDescription(f"打开{title}任务创建页面")

        layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setProperty("heading", True)
        self.state_label = QLabel(self._state_text(registry, module_id))
        self.open_button = QPushButton("开始使用")
        self.open_button.setAccessibleName(f"打开{title}")
        self.open_button.clicked.connect(lambda checked=False: self.activated.emit(self.module_id))
        layout.addWidget(self.title_label)
        layout.addWidget(self.state_label)
        layout.addWidget(self.open_button)

    @staticmethod
    def _state_text(registry: object, module_id: object) -> str:
        try:
            module = registry.get(module_id)
        except KeyError:
            return "未安装 · 状态未知"
        source = "模拟模块" if module.is_mock else "正式模块"
        health = "健康" if module.health == "healthy" else "异常"
        return f"已安装 · {source} · {health}"
