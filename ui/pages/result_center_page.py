from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.contracts.result import ModuleResult
from ui.widgets.output_files import OutputFilesWidget


class ResultCenterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("workflow-result-center")
        self.current_result: ModuleResult | None = None
        layout = QVBoxLayout(self)
        title = QLabel("结果中心")
        title.setProperty("heading", True)
        self.status_label = QLabel("暂无任务结果")
        self.summary_label = QLabel()
        self.output_files = OutputFilesWidget()
        layout.addWidget(title)
        layout.addWidget(self.status_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.output_files)

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
