from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
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
    job_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page-confirmations")
        self.current_job_id = ""
        self._models: dict[str, list[ConfirmationPrompt]] = {}
        self._submitting_jobs: set[str] = set()
        self.prompts: list[ConfirmationPrompt] = []
        self.answer_inputs: dict[str, QLineEdit] = {}
        self.batch_checks: dict[str, QCheckBox] = {}
        self.remember_checks: dict[str, QCheckBox] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        title = QLabel("待确认事项")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("只在规则边界、字段歧义或高风险判断出现时请求人工决定。")
        subtitle.setProperty("subtle", True)
        self.status_label = QLabel("当前没有待确认事项")
        self.status_label.setProperty("section", True)
        self.job_selector = QComboBox()
        self.job_selector.setAccessibleName("选择待确认任务")
        self.job_selector.currentIndexChanged.connect(self._selector_changed)
        self.form_host = QWidget()
        self.form_layout = QFormLayout(self.form_host)
        self.form_layout.setVerticalSpacing(14)
        self.submit_button = QPushButton("提交确认")
        self.submit_button.setProperty("primary", True)
        self.submit_button.setAccessibleName("提交确认答案")
        self.submit_button.setEnabled(False)
        self.submit_button.clicked.connect(self._submit)
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(14)
        card_layout.addWidget(self.status_label)
        card_layout.addWidget(self.job_selector)
        card_layout.addWidget(self.form_host)
        card_layout.addWidget(self.submit_button, 0)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch()

    def load(self, job_id: str, prompts: list[ConfirmationPrompt]) -> None:
        is_new = job_id not in self._models
        self._models[job_id] = list(prompts)
        if is_new:
            self.job_selector.blockSignals(True)
            self.job_selector.addItem(job_id, job_id)
            self.job_selector.blockSignals(False)
        if not self.current_job_id:
            self.select_job(job_id, user_selected=False)
        elif self.current_job_id == job_id:
            self._render(job_id)

    @property
    def pending_job_ids(self) -> tuple[str, ...]:
        return tuple(self._models)

    def select_job(self, job_id: str, *, user_selected: bool = True) -> None:
        if job_id not in self._models:
            raise KeyError(job_id)
        index = self.job_selector.findData(job_id)
        if index >= 0 and self.job_selector.currentIndex() != index:
            self.job_selector.blockSignals(True)
            self.job_selector.setCurrentIndex(index)
            self.job_selector.blockSignals(False)
        self._render(job_id)
        if user_selected:
            self.job_selected.emit(job_id)

    def remove(self, job_id: str) -> None:
        self._models.pop(job_id, None)
        self._submitting_jobs.discard(job_id)
        index = self.job_selector.findData(job_id)
        if index >= 0:
            self.job_selector.blockSignals(True)
            self.job_selector.removeItem(index)
            self.job_selector.blockSignals(False)
        if self.current_job_id == job_id:
            self.current_job_id = ""
            self.prompts = []
            self._clear_form()
            if self.job_selector.count():
                next_job = str(self.job_selector.itemData(0))
                self.select_job(next_job, user_selected=False)
            else:
                self.status_label.setText("当前没有待确认事项")
                self.submit_button.setEnabled(False)

    def submission_failed(self, job_id: str) -> None:
        self._submitting_jobs.discard(job_id)
        if self.current_job_id == job_id and job_id in self._models:
            self.submit_button.setEnabled(True)

    def _render(self, job_id: str) -> None:
        self._clear_form()
        self.current_job_id = job_id
        prompts = self._models[job_id]
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
        self.submit_button.setEnabled(
            bool(job_id) and bool(prompts) and job_id not in self._submitting_jobs
        )

    def _selector_changed(self, index: int) -> None:
        if index < 0:
            return
        job_id = str(self.job_selector.itemData(index))
        if job_id in self._models:
            self.select_job(job_id)

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
            job_id = self.current_job_id
            if job_id in self._submitting_jobs:
                return
            self._submitting_jobs.add(job_id)
            self.submit_button.setEnabled(False)
            self.submitted.emit(job_id, answers)
