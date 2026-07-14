from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from core.contracts.result import ModuleResult
from ui.widgets.output_files import OutputFilesWidget


class ResultCenterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-result-center")
        self.current_result: ModuleResult | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        title = QLabel("结果中心")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("查看本次处理摘要并打开模块生成的本地成果文件。")
        subtitle.setProperty("subtle", True)
        self.status_label = QLabel("暂无任务结果")
        self.summary_label = QLabel()
        self.output_files = OutputFilesWidget()
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)
        self.status_label.setProperty("section", True)
        card_layout.addWidget(self.status_label)
        card_layout.addWidget(self.summary_label)
        card_layout.addWidget(self.output_files)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch()

    @property
    def output_buttons(self) -> list[QPushButton]:
        return self.output_files.buttons

    def show_result(self, result: ModuleResult) -> None:
        self.current_result = result
        self.status_label.setText(f"任务状态：{result.status.value}")
        self.summary_label.setText(
            f"输入 {result.summary.input_count}，"
            f"成功处理 {result.summary.processed_count}，"
            f"失败 {result.summary.failed_count}"
        )
        self.output_files.set_outputs(result.outputs)
