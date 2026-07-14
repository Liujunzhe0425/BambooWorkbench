from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from core.contracts.progress import ProgressEvent


class TaskProgressPage(QWidget):
    cancel_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-task-progress")
        self.current_job_id = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        title = QLabel("任务进度")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("处理过程保留状态与日志，可随时回到任务历史查看。")
        subtitle.setProperty("subtle", True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setAccessibleName("任务完成进度")
        self.message_label = QLabel("等待任务开始")
        self.message_label.setAccessibleName("任务进度说明")
        self.cancel_button = QPushButton("取消任务")
        self.cancel_button.setAccessibleName("取消当前任务")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._request_cancel)
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(16)
        status = QLabel("正在处理")
        status.setProperty("section", True)
        card_layout.addWidget(status)
        card_layout.addWidget(self.progress_bar)
        card_layout.addWidget(self.message_label)
        card_layout.addWidget(self.cancel_button)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch()

    def bind(self, job_id: str) -> None:
        self.current_job_id = job_id
        self.progress_bar.setValue(0)
        self.message_label.setText("任务已创建，等待处理")
        self.cancel_button.setEnabled(bool(job_id))

    def update_progress(self, event: ProgressEvent) -> None:
        self.progress_bar.setValue(event.percent)
        self.message_label.setText(event.message)

    def _request_cancel(self) -> None:
        if self.current_job_id:
            self.cancel_requested.emit(self.current_job_id)
