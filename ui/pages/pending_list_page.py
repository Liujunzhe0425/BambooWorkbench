"""Cross-module list of tasks that are waiting for human confirmation."""

from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.storage.repositories.tasks import TaskRepository

_MODULE_NAMES = {
    "moisture": "竹丝水分",
    "boiling": "水煮模块",
    "after_sales": "售后分析",
}


class PendingListPage(QWidget):
    task_requested = Signal(str)

    def __init__(self, repository: TaskRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setObjectName("page-pending-list")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        title = QLabel("待确认清单")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("仅展示仍在等待人工确认的任务，按创建时间从新到旧排列。")
        subtitle.setProperty("subtle", True)
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["任务名称", "任务 ID", "模块", "所属年月", "创建时间", "待确认数量"]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.cellClicked.connect(self._open)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.empty = QLabel("当前没有等待人工确认的任务。")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.table)
        card_layout.addWidget(self.empty)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card, 1)
        self.refresh()

    def refresh(self) -> None:
        rows = self.repository.list_waiting_confirmation()
        self.table.setRowCount(len(rows))
        for row, record in enumerate(rows):
            year = record.get("period_year")
            month = record.get("period_month")
            values = (
                record.get("task_name") or f"任务 {record['job_id']}",
                record["job_id"],
                _MODULE_NAMES.get(str(record["module_id"]), str(record["module_id"])),
                f"{year}年{int(month):02d}月" if year and month else "未登记",
                _display_time(str(record["created_at"])),
                record["confirmation_count"],
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, str(record["job_id"]))
                self.table.setItem(row, column, item)
        self.table.setVisible(bool(rows))
        self.empty.setVisible(not rows)

    def _open(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is not None:
            self.task_requested.emit(str(item.data(Qt.ItemDataRole.UserRole)))


def _display_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return value.replace("T", " ", 1)
