from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from core.contracts.enums import ModuleId
from ui.widgets.module_card import ModuleCard


class WorkbenchPage(QWidget):
    module_selected = Signal(object)

    def __init__(self, registry: object) -> None:
        super().__init__()
        installed_modules = tuple(registry.all())
        installed_count = len(installed_modules)
        real_count = sum(not module.is_mock for module in installed_modules)
        mock_count = installed_count - real_count
        missing_count = max(3 - installed_count, 0)
        self.setObjectName("page-workbench")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        self.company_label = QLabel("湖南桃花江竹材科技股份有限公司")
        self.company_label.setProperty("pageTitle", True)
        self.subtitle_label = QLabel("竹材品质数据智能工作台")
        self.subtitle_label.setProperty("subtle", True)
        header_text.addWidget(self.company_label)
        header_text.addWidget(self.subtitle_label)
        self.connection_label = QLabel("●  离线核心可用")
        self.connection_label.setObjectName("connectionPill")
        header.addLayout(header_text)
        header.addStretch()
        header.addWidget(self.connection_label)
        layout.addLayout(header)

        hero = QFrame()
        hero.setObjectName("workbenchHero")
        hero.setProperty("card", True)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 20, 24, 20)
        hero_layout.setSpacing(6)
        self.product_label = QLabel("竹简工作台")
        self.product_label.setProperty("eyebrow", True)
        self.product_label.setAccessibleName("产品名称：竹简工作台")
        hero_title = QLabel("让品质数据沿着竹节自然生长")
        hero_title.setObjectName("heroTitle")
        if mock_count:
            hero_message = "当前为显式演示模式，模拟模块仅用于界面与流程演示。"
        elif real_count:
            hero_message = f"已加载 {real_count} 个正式业务模块，可直接处理文件并生成成果。"
        else:
            hero_message = "当前未检测到正式业务模块，三个入口将保留为未安装占位状态。"
        hero_subtitle = QLabel(f"统一入口承载三个业务模块；{hero_message}")
        hero_subtitle.setProperty("subtle", True)
        hero_subtitle.setWordWrap(True)
        hero_layout.addWidget(self.product_label)
        hero_layout.addWidget(hero_title)
        hero_layout.addWidget(hero_subtitle)
        layout.addWidget(hero)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        titles = {
            ModuleId.MOISTURE: (
                "竹",
                "原竹丝水分检测",
                "接入后批量读取水分数据，生成汇总表、趋势与异常提示。",
            ),
            ModuleId.BOILING: (
                "煮",
                "水煮实验",
                "接入后复核密度、膨胀率与浸渍剥离结果，保留待确认边界。",
            ),
            ModuleId.AFTER_SALES: (
                "售",
                "售后分析",
                "接入后统一问题分类、责任费用与关闭统计，输出报表与图表。",
            ),
        }
        self.cards: dict[ModuleId, ModuleCard] = {}
        for column, (module_id, (badge, title, description)) in enumerate(titles.items()):
            card = ModuleCard(module_id, title, registry, badge, description)
            card.activated.connect(self.module_selected)
            self.cards[module_id] = card
            grid.addWidget(card, 0, column)
        layout.addLayout(grid)

        overview = QHBoxLayout()
        overview.setSpacing(14)
        readiness = self._overview_card()
        readiness_layout = readiness.layout()
        readiness_header = QHBoxLayout()
        readiness_title = QLabel("框架准备度")
        readiness_title.setProperty("metricTitle", True)
        readiness_value = QLabel(f"模块接入 {installed_count}/3")
        readiness_value.setProperty("metricValue", True)
        readiness_header.addWidget(readiness_title)
        readiness_header.addStretch()
        readiness_header.addWidget(readiness_value)
        self.readiness_bar = QProgressBar()
        self.readiness_bar.setRange(0, 100)
        self.readiness_bar.setValue(round(installed_count / 3 * 100))
        self.readiness_bar.setTextVisible(False)
        badges = QLabel(
            f"正式 {real_count}   ·   演示 {mock_count}   ·   待接入 {missing_count}"
        )
        badges.setProperty("smallPill", True)
        readiness_layout.addLayout(readiness_header)
        readiness_layout.addWidget(self.readiness_bar)
        readiness_layout.addWidget(badges)

        today = self._overview_card()
        today_layout = today.layout()
        today_header = QHBoxLayout()
        today_title = QLabel("今日任务")
        today_title.setProperty("metricTitle", True)
        today_value = QLabel("模块可用" if installed_count else "等待模块接入")
        today_value.setProperty("metricValue", True)
        today_header.addWidget(today_title)
        today_header.addStretch()
        today_header.addWidget(today_value)
        today_hint = QLabel("当前 0 项待确认，接入模块后任务将在此统一跟踪。")
        today_hint.setProperty("subtle", True)
        today_hint.setWordWrap(True)
        today_layout.addLayout(today_header)
        today_layout.addWidget(today_hint)
        today_layout.addStretch()

        overview.addWidget(readiness, 3)
        overview.addWidget(today, 2)
        layout.addLayout(overview)
        layout.addStretch()

    @staticmethod
    def _overview_card() -> QFrame:
        card = QFrame()
        card.setProperty("card", True)
        card.setProperty("compactCard", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 14, 18, 14)
        card_layout.setSpacing(9)
        return card
