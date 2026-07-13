from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from core.contracts.enums import ModuleId
from ui.widgets.module_card import ModuleCard


class WorkbenchPage(QWidget):
    module_selected = Signal(object)

    def __init__(self, registry: object) -> None:
        super().__init__()
        self.setObjectName("page-workbench")
        layout = QVBoxLayout(self)
        self.company_label = QLabel("湖南桃花江竹材科技股份有限公司")
        self.company_label.setProperty("heading", True)
        self.product_label = QLabel("竹简工作台")
        self.product_label.setAccessibleName("产品名称：竹简工作台")
        self.subtitle_label = QLabel("竹材品质数据智能工作台")
        layout.addWidget(self.company_label)
        layout.addWidget(self.product_label)
        layout.addWidget(self.subtitle_label)

        grid = QGridLayout()
        titles = {
            ModuleId.MOISTURE: "原竹丝水分检测",
            ModuleId.BOILING: "水煮实验",
            ModuleId.AFTER_SALES: "售后统计",
        }
        self.cards: dict[ModuleId, ModuleCard] = {}
        for column, (module_id, title) in enumerate(titles.items()):
            card = ModuleCard(module_id, title, registry)
            card.activated.connect(self.module_selected)
            self.cards[module_id] = card
            grid.addWidget(card, 0, column)
        layout.addLayout(grid)
        layout.addStretch()
