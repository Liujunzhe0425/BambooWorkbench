from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.storage.repositories.tasks import TaskRepository


class HistoryPage(QWidget):
    _COLUMNS = (
        ("job_id", "任务 ID"),
        ("module_id", "模块"),
        ("status", "状态"),
        ("created_at", "创建时间"),
        ("updated_at", "更新时间"),
    )

    def __init__(self, repository: TaskRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setObjectName("page-history")
        self.setAccessibleName("任务历史")

        layout = QVBoxLayout(self)
        title = QLabel("任务历史")
        title.setProperty("heading", True)
        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setObjectName("historyTable")
        self.table.setAccessibleName("历史任务列表")
        self.table.setHorizontalHeaderLabels([label for _, label in self._COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(title)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        records = self.repository.list_recent()
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            for column, (field, _label) in enumerate(self._COLUMNS):
                self.table.setItem(row, column, QTableWidgetItem(str(record[field])))
