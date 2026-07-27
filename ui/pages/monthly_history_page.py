"""Twelve-month official-result ledger for one module and year."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.storage.repositories.monthly import MonthlyRepository

_MODULES = (
    ("moisture", "竹丝水分"),
    ("boiling", "水煮模块"),
    ("after_sales", "售后分析"),
)


class MonthlyHistoryPage(QWidget):
    result_requested = Signal(str)
    governance_requested = Signal(str, str, int, int)

    def __init__(self, repository: MonthlyRepository) -> None:
        super().__init__()
        self.repository = repository
        self.module_id = "moisture"
        self._columns = 4
        self.setObjectName("page-monthly-history")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        title = QLabel("历史数据")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("按年份和模块查看当前正式月度结果。每张卡片打开该月完整累计成果。")
        subtitle.setProperty("subtle", True)
        controls = QHBoxLayout()
        self.year_combo = QComboBox()
        current = datetime.now().year
        for year in range(2077, 1999, -1):
            self.year_combo.addItem(str(year), year)
        self.year_combo.setCurrentIndex(self.year_combo.findData(current))
        self.year_combo.setAccessibleName("历史数据年份")
        self.module_buttons: dict[str, QPushButton] = {}
        controls.addWidget(QLabel("年份"))
        controls.addWidget(self.year_combo)
        controls.addStretch()
        for module_id, label in _MODULES:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("secondary", True)
            button.setProperty("historyModule", True)
            button.clicked.connect(
                lambda _checked=False, selected=module_id: self.select_module(selected)
            )
            self.module_buttons[module_id] = button
            controls.addWidget(button)
        controls.addStretch()
        self.grid_host = QWidget()
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(14)
        self.cards: list[QPushButton] = []
        for month in range(1, 13):
            card = QPushButton()
            card.setMinimumSize(170, 104)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            card.setProperty("monthCard", True)
            card.setAccessibleName(f"{month}月历史结果")
            card.clicked.connect(
                lambda _checked=False, selected_month=month: self._open_month(selected_month)
            )
            self.cards.append(card)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(self.grid_host)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(controls)
        layout.addWidget(scroll, 1)
        self.year_combo.currentIndexChanged.connect(self.refresh)
        self.select_module("moisture")

    @property
    def year(self) -> int:
        return int(self.year_combo.currentData())

    def select_module(self, module_id: str) -> None:
        if module_id not in self.module_buttons:
            raise ValueError("unknown history module")
        self.module_id = module_id
        for candidate, button in self.module_buttons.items():
            button.setChecked(candidate == module_id)
        self.refresh()

    def refresh(self) -> None:
        slots = {
            int(record["month"]): record
            for record in self.repository.list_year(self.module_id, self.year)
        }
        active = self.repository.active_months(self.module_id, self.year)
        for month, card in enumerate(self.cards, 1):
            record = slots.get(month)
            if month in active:
                card.setText(f"{month} 月\n重算中")
                card.setEnabled(False)
                card.setStyleSheet(
                    "background:#FFF3CD;color:#664D03;border:1px solid #E7C96B;"
                    "border-radius:10px;font-weight:600;"
                )
                card.setProperty("job_id", None)
                card.setProperty("broken", False)
            elif record is None:
                card.setText(f"{month} 月\n未创建")
                card.setEnabled(False)
                card.setStyleSheet(
                    "background:#E9ECEF;color:#6C757D;border:1px solid #CED4DA;"
                    "border-radius:10px;font-weight:600;"
                )
                card.setProperty("job_id", None)
                card.setProperty("broken", False)
            else:
                integrity = str(record.get("result_integrity", "unknown"))
                broken = integrity in {"missing", "invalid", "conflict"}
                card.setText(f"{month} 月\n{'成果异常' if broken else '已创建'}")
                card.setEnabled(True)
                card.setStyleSheet(
                    (
                        "background:#F8D7DA;color:#842029;border:1px solid #E6AEB3;"
                        if broken
                        else "background:#DDF0E3;color:#205C3B;border:1px solid #9BC9AA;"
                    )
                    + "border-radius:10px;font-weight:600;"
                )
                card.setProperty("job_id", str(record["official_job_id"]))
                card.setProperty("broken", broken)
        self._relayout()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        width = event.size().width()
        columns = 4 if width >= 820 else 3 if width >= 620 else 2
        if columns != self._columns:
            self._columns = columns
            self._relayout()

    def _relayout(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0)
        for index in range(12):
            self.grid.setColumnStretch(index, 0)
            self.grid.setRowStretch(index, 0)
        for index, card in enumerate(self.cards):
            self.grid.addWidget(card, index // self._columns, index % self._columns)
        for column in range(self._columns):
            self.grid.setColumnStretch(column, 1)
        rows = (len(self.cards) + self._columns - 1) // self._columns
        for row in range(rows):
            self.grid.setRowStretch(row, 1)
        self.grid.setAlignment(Qt.AlignmentFlag(0))

    def _open_month(self, month: int) -> None:
        job_id = self.cards[month - 1].property("job_id")
        if isinstance(job_id, str) and job_id:
            if bool(self.cards[month - 1].property("broken")):
                self.governance_requested.emit(
                    job_id, self.module_id, self.year, month
                )
            else:
                self.result_requested.emit(job_id)
