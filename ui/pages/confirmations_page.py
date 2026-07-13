from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.result import ConfirmationPrompt


class ConfirmationsPage(QWidget):
    submitted = Signal(str, list)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-confirmations")
        self.current_job_id = ""
        self.prompts: list[ConfirmationPrompt] = []
        self.answer_inputs: dict[str, QLineEdit] = {}
        self.batch_checks: dict[str, QCheckBox] = {}
        self.remember_checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        title = QLabel("待确认事项")
        title.setProperty("heading", True)
        self.status_label = QLabel("当前没有待确认事项")
        self.form_host = QWidget()
        self.form_layout = QFormLayout(self.form_host)
        self.submit_button = QPushButton("提交确认")
        self.submit_button.setProperty("primary", True)
        self.submit_button.setAccessibleName("提交确认答案")
        self.submit_button.setEnabled(False)
        self.submit_button.clicked.connect(self._submit)
        layout.addWidget(title)
        layout.addWidget(self.status_label)
        layout.addWidget(self.form_host)
        layout.addWidget(self.submit_button)
        layout.addStretch()

    def load(self, job_id: str, prompts: list[ConfirmationPrompt]) -> None:
        self._clear_form()
        self.current_job_id = job_id
        self.prompts = list(prompts)
        self.status_label.setText(f"任务 {job_id} 需要确认 {len(prompts)} 项")
        for prompt in prompts:
            editor_host = QWidget()
            editor_layout = QVBoxLayout(editor_host)
            editor_layout.setContentsMargins(0, 0, 0, 0)
            answer = QLineEdit()
            suggested = prompt.suggested_value
            if suggested is None and prompt.options:
                suggested = prompt.options[0]
            answer.setText("" if suggested is None else str(suggested))
            answer.setAccessibleName(f"{prompt.field}的确认答案")
            answer.setAccessibleDescription(prompt.reason)
            self.answer_inputs[prompt.confirmation_id] = answer
            editor_layout.addWidget(answer)
            if prompt.batch_applicable:
                batch = QCheckBox("应用到本批次")
                batch.setAccessibleName(f"将{prompt.field}应用到本批次")
                self.batch_checks[prompt.confirmation_id] = batch
                editor_layout.addWidget(batch)
            if prompt.rememberable:
                remember = QCheckBox("记住该映射")
                remember.setAccessibleName(f"记住{prompt.field}映射")
                self.remember_checks[prompt.confirmation_id] = remember
                editor_layout.addWidget(remember)
            label = f"{prompt.field}（{'必填' if prompt.blocking else '可选'}）"
            self.form_layout.addRow(label, editor_host)
        self.submit_button.setEnabled(bool(job_id) and bool(prompts))

    def _clear_form(self) -> None:
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)
        self.answer_inputs.clear()
        self.batch_checks.clear()
        self.remember_checks.clear()

    def _submit(self) -> None:
        answers: list[ConfirmationAnswer] = []
        for prompt in self.prompts:
            batch = self.batch_checks.get(prompt.confirmation_id)
            remember = self.remember_checks.get(prompt.confirmation_id)
            answers.append(
                ConfirmationAnswer(
                    confirmation_id=prompt.confirmation_id,
                    value=self.answer_inputs[prompt.confirmation_id].text(),
                    apply_to_batch=batch.isChecked() if batch is not None else False,
                    remember_mapping=(remember.isChecked() if remember is not None else False),
                )
            )
        if self.current_job_id and answers:
            self.submitted.emit(self.current_job_id, answers)
