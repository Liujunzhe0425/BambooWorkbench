from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.storage.repositories.tasks import TaskRepository


class HistoryPage(QWidget):
    result_requested = Signal(str)

    _COLUMNS = (
        ("task_number", "编号"),
        ("module_id", "业务模块"),
        ("status", "状态"),
        ("created_at", "创建时间"),
        ("updated_at", "更新时间"),
    )
    _MODULE_NAMES = {
        "moisture": "原竹丝水分检测",
        "boiling": "水煮实验",
        "after_sales": "售后分析",
    }
    _STATUS_NAMES = {
        "created": "已创建",
        "running_draft": "正在读取与分析",
        "waiting_confirmation": "待确认",
        "running_finalize": "正在生成结果",
        "success": "已完成",
        "partial_success": "部分完成",
        "needs_confirmation": "待确认",
        "failed": "失败",
        "cancelled": "已取消",
        "running": "处理中",
    }

    def __init__(
        self,
        repository: TaskRepository,
        status_resolver: Callable[[dict[str, object]], str] | None = None,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.status_resolver = status_resolver
        self.setObjectName("page-history")
        self.setAccessibleName("任务历史")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(18)
        title = QLabel("任务历史")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("统一查看三个模块的执行记录、处理状态与更新时间。")
        subtitle.setProperty("subtle", True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        summary = QGridLayout()
        summary.setHorizontalSpacing(12)
        self.total_value = self._summary_card(summary, 0, "全部任务", "0", "已记录")
        self.success_value = self._summary_card(summary, 1, "已完成", "0", "可追溯")
        self.pending_value = self._summary_card(summary, 2, "待确认", "0", "需要人工复核")
        layout.addLayout(summary)

        table_card = QFrame()
        table_card.setProperty("card", True)
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)
        table_header = QHBoxLayout()
        table_title = QLabel("最近任务")
        table_title.setProperty("section", True)
        table_hint = QLabel("只展示可追溯的任务元数据")
        table_hint.setProperty("subtle", True)
        table_header.addWidget(table_title)
        table_header.addStretch()
        table_header.addWidget(table_hint)

        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setObjectName("historyTable")
        self.table.setAccessibleName("历史任务列表")
        self.table.setHorizontalHeaderLabels([label for _, label in self._COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setCursor(Qt.CursorShape.PointingHandCursor)
        self.table.cellClicked.connect(self._open_result)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        header = self.table.horizontalHeader()
        for column in range(len(self._COLUMNS)):
            mode = QHeaderView.ResizeMode.Stretch
            if column in {0, 2}:
                mode = QHeaderView.ResizeMode.ResizeToContents
            header.setSectionResizeMode(column, mode)
        self.empty_label = QLabel("暂无任务记录。待业务模块接入后，处理历史将在此自动汇总。")
        self.empty_label.setObjectName("historyEmptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        table_layout.addLayout(table_header)
        table_layout.addWidget(self.table, 1)
        table_layout.addWidget(self.empty_label)
        layout.addWidget(table_card, 1)
        self.refresh()

    @staticmethod
    def _summary_card(
        layout: QGridLayout,
        column: int,
        title: str,
        value: str,
        hint: str,
    ) -> QLabel:
        card = QFrame()
        card.setProperty("card", True)
        card.setProperty("statCard", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 13, 16, 13)
        card_layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setProperty("subtle", True)
        value_label = QLabel(value)
        value_label.setProperty("statValue", True)
        hint_label = QLabel(hint)
        hint_label.setProperty("caption", True)
        card_layout.addWidget(title_label)
        card_layout.addWidget(value_label)
        card_layout.addWidget(hint_label)
        layout.addWidget(card, 0, column)
        return value_label

    def refresh(self) -> None:
        records = self.repository.list_recent()
        self.table.setRowCount(len(records))
        successes = 0
        pending = 0
        for row, record in enumerate(records):
            raw_status = (
                self.status_resolver(record)
                if self.status_resolver is not None
                else str(record["status"])
            )
            successes += raw_status in {"success", "partial_success"}
            pending += raw_status in {"needs_confirmation", "waiting_confirmation"}
            for column, (field, _label) in enumerate(self._COLUMNS):
                raw_value = str(record[field])
                if field == "module_id":
                    raw_value = self._MODULE_NAMES.get(raw_value, raw_value)
                elif field == "status":
                    raw_value = self._STATUS_NAMES.get(raw_value, raw_value)
                elif field in {"created_at", "updated_at"}:
                    raw_value = self._display_time(raw_value)
                item = QTableWidgetItem(raw_value)
                item.setData(Qt.ItemDataRole.UserRole, str(record["job_id"]))
                item.setData(Qt.ItemDataRole.UserRole + 1, raw_status)
                if raw_status in {"success", "partial_success"}:
                    item.setToolTip("单击查看本次任务结果")
                if field == "status":
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)
        self.total_value.setText(str(len(records)))
        self.success_value.setText(str(successes))
        self.pending_value.setText(str(pending))
        self.table.setVisible(bool(records))
        self.empty_label.setVisible(not records)

    def _open_result(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        if item.data(Qt.ItemDataRole.UserRole + 1) not in {"success", "partial_success"}:
            return
        job_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(job_id, str) and job_id:
            self.result_requested.emit(job_id)

    @staticmethod
    def _display_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value.replace("T", " ", 1)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
