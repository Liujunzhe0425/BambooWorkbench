from collections import Counter, defaultdict
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.contracts.confirmation import ConfirmationAnswer
from core.contracts.result import ConfirmationPrompt

_FIELD_LABELS = {
    "default_year": "业务年份",
    "product_usage": "产品用途",
    "density": "密度结论复核",
    "密度": "密度结论复核",
    "density_g_cm3": "密度数值冲突",
    "expansion": "膨胀率结论复核",
    "expansion_ratio": "膨胀率数值冲突",
    "expansion_review": "膨胀情况复核",
}

_BATCH_HELP = (
    "勾选后，本次填写的答案会应用到当前任务中其他适用的同类文件或记录。"
    "只有确认本批数据应使用同一答案时才勾选；不同文件情况不一致时请勿勾选。"
)


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
        self.answer_inputs: dict[str, QLineEdit | QComboBox] = {}
        self.batch_checks: dict[str, QCheckBox] = {}
        self.batch_help_labels: dict[str, QLabel] = {}
        self.remember_checks: dict[str, QCheckBox] = {}
        self.reason_labels: dict[str, QLabel] = {}
        self.source_labels: dict[str, QLabel] = {}
        self.file_group_frames: dict[str, QFrame] = {}
        self.file_group_titles: dict[str, QLabel] = {}
        self.prompt_group_keys: dict[str, str] = {}

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
        self.form_layout = QVBoxLayout(self.form_host)
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(14)
        self.submit_button = QPushButton("提交确认")
        self.submit_button.setProperty("primary", True)
        self.submit_button.setAccessibleName("提交确认答案")
        self.submit_button.setEnabled(False)
        self.submit_button.clicked.connect(self._submit)
        self.card = QFrame()
        self.card.setProperty("card", True)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(14)
        card_layout.addWidget(self.status_label)
        card_layout.addWidget(self.job_selector)
        card_layout.addWidget(self.form_host)
        card_layout.addWidget(self.submit_button, 0)
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("confirmationScrollContent")
        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(self.card)
        scroll_layout.addStretch()
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("confirmationScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.scroll_area, 1)

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
        grouped = self._group_prompts(prompts)
        file_group_total = sum(bool(group_key) for group_key, _items in grouped)
        file_group_position = 0
        for group_key, group_prompts in grouped:
            if group_key:
                file_group_position += 1
            self._add_file_group(
                group_key,
                group_prompts,
                file_group_position,
                file_group_total,
            )
        self.form_layout.addStretch()
        self.form_host.setMinimumHeight(self.form_layout.sizeHint().height())
        self.scroll_content.setMinimumHeight(self.card.sizeHint().height())
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
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.answer_inputs.clear()
        self.batch_checks.clear()
        self.batch_help_labels.clear()
        self.remember_checks.clear()
        self.reason_labels.clear()
        self.source_labels.clear()
        self.file_group_frames.clear()
        self.file_group_titles.clear()
        self.prompt_group_keys.clear()
        self.form_host.setMinimumHeight(0)
        self.scroll_content.setMinimumHeight(0)

    @staticmethod
    def _group_prompts(
        prompts: list[ConfirmationPrompt],
    ) -> list[tuple[str, list[ConfirmationPrompt]]]:
        grouped: dict[str, list[ConfirmationPrompt]] = {}
        for prompt in prompts:
            group_key = str(prompt.source.source_file or "").strip()
            grouped.setdefault(group_key, []).append(prompt)
        # Missing-source prompts always appear in the final compatibility group.
        return sorted(grouped.items(), key=lambda item: not bool(item[0]))

    def _add_file_group(
        self,
        group_key: str,
        prompts: list[ConfirmationPrompt],
        position: int,
        total: int,
    ) -> None:
        frame = QFrame()
        frame.setProperty("confirmationFileGroup", True)
        frame.setAccessibleName(
            Path(group_key).name if group_key else "其他确认事项"
        )
        group_layout = QVBoxLayout(frame)
        group_layout.setContentsMargins(16, 14, 16, 16)
        group_layout.setSpacing(12)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        if group_key:
            counter = QLabel(f"第 {position} 份 / 共 {total} 份")
            filename = Path(group_key).name
        else:
            counter = QLabel("兼容分组")
            filename = "其他确认事项"
        counter.setProperty("confirmationFileCounter", True)
        title = QLabel(filename)
        title.setProperty("confirmationFileName", True)
        title.setWordWrap(True)
        title.setToolTip(group_key or "未提供来源文件的确认事项")
        header_layout.addWidget(counter, 0)
        header_layout.addWidget(title, 1)
        group_layout.addWidget(header)

        fields = QWidget()
        fields_layout = QGridLayout(fields)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setHorizontalSpacing(14)
        fields_layout.setVerticalSpacing(12)
        field_totals = Counter(prompt.field for prompt in prompts)
        field_positions: defaultdict[str, int] = defaultdict(int)
        columns = 3
        for index, prompt in enumerate(prompts):
            field_positions[prompt.field] += 1
            editor_host = self._build_prompt_editor(
                prompt,
                field_positions[prompt.field],
                field_totals[prompt.field],
            )
            fields_layout.addWidget(editor_host, index // columns, index % columns)
            fields_layout.setColumnStretch(index % columns, 1)
            self.prompt_group_keys[prompt.confirmation_id] = group_key
        group_layout.addWidget(fields)

        self.file_group_frames[group_key] = frame
        self.file_group_titles[group_key] = title
        self.form_layout.addWidget(frame)

    def _build_prompt_editor(
        self,
        prompt: ConfirmationPrompt,
        position: int,
        total: int,
    ) -> QWidget:
        editor_host = QWidget()
        editor_host.setProperty("confirmationField", True)
        editor_host.setMinimumWidth(220)
        editor_layout = QVBoxLayout(editor_host)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(6)

        label = QLabel(self._prompt_label(prompt, position, total))
        label.setProperty("confirmationFieldLabel", True)
        label.setWordWrap(True)
        editor_layout.addWidget(label)

        suggested = prompt.suggested_value
        if suggested is None and prompt.options:
            suggested = prompt.options[0]
        if prompt.options:
            answer: QLineEdit | QComboBox = QComboBox()
            for option in prompt.options:
                answer.addItem(str(option), option)
            suggested_text = "" if suggested is None else str(suggested)
            selected_index = answer.findText(suggested_text)
            if selected_index < 0 and suggested_text:
                answer.addItem(suggested_text, suggested)
                selected_index = answer.count() - 1
            if selected_index >= 0:
                answer.setCurrentIndex(selected_index)
        else:
            answer = QLineEdit()
            answer.setText("" if suggested is None else str(suggested))
        answer.setAccessibleName(f"{prompt.field}的确认答案")
        answer.setAccessibleDescription(prompt.reason)
        self.answer_inputs[prompt.confirmation_id] = answer
        editor_layout.addWidget(answer)

        reason = QLabel(prompt.reason)
        reason.setWordWrap(True)
        reason.setProperty("confirmationReason", True)
        reason.setAccessibleName(f"{prompt.field}确认原因")
        self.reason_labels[prompt.confirmation_id] = reason
        editor_layout.addWidget(reason)

        source = QLabel(self._source_location_text(prompt))
        source.setWordWrap(True)
        source.setProperty("confirmationSource", True)
        source.setAccessibleName(f"{prompt.field}数据来源")
        source.setAccessibleDescription(self._source_text(prompt))
        self.source_labels[prompt.confirmation_id] = source
        editor_layout.addWidget(source)

        if prompt.batch_applicable:
            batch = QCheckBox("应用到本批次")
            batch.setAccessibleName(f"将{prompt.field}应用到本批次")
            batch.setAccessibleDescription(_BATCH_HELP)
            batch.setToolTip(_BATCH_HELP)
            self.batch_checks[prompt.confirmation_id] = batch
            help_label = QLabel("!")
            help_label.setProperty("helpBadge", True)
            help_label.setToolTip(_BATCH_HELP)
            help_label.setAccessibleName("应用到本批次说明")
            help_label.setAccessibleDescription(_BATCH_HELP)
            self.batch_help_labels[prompt.confirmation_id] = help_label
            batch_row = QWidget()
            batch_layout = QHBoxLayout(batch_row)
            batch_layout.setContentsMargins(0, 0, 0, 0)
            batch_layout.setSpacing(7)
            batch_layout.addWidget(batch)
            batch_layout.addWidget(help_label)
            batch_layout.addStretch()
            editor_layout.addWidget(batch_row)
        if prompt.rememberable:
            remember = QCheckBox("记住该映射")
            remember.setAccessibleName(f"记住{prompt.field}映射")
            self.remember_checks[prompt.confirmation_id] = remember
            editor_layout.addWidget(remember)
        editor_layout.addStretch()
        return editor_host

    @staticmethod
    def _prompt_label(prompt: ConfirmationPrompt, position: int, total: int) -> str:
        label = _FIELD_LABELS.get(prompt.field, prompt.field)
        if total > 1:
            label = f"{label} {position}/{total}"
        requirement = "必填" if prompt.blocking else "可选"
        return f"{label}（{requirement}）"

    @staticmethod
    def _source_text(prompt: ConfirmationPrompt) -> str:
        source = prompt.source
        parts = [Path(source.source_file).name]
        if source.sheet:
            parts.append(str(source.sheet).strip())
        if source.cell_or_range:
            parts.append(source.cell_or_range)
        return "来源：" + " · ".join(part for part in parts if part)

    @staticmethod
    def _source_location_text(prompt: ConfirmationPrompt) -> str:
        source = prompt.source
        parts: list[str] = []
        if source.sheet:
            parts.append(str(source.sheet).strip())
        if source.cell_or_range:
            parts.append(source.cell_or_range)
        return "位置：" + (" · ".join(parts) if parts else "未提供工作表位置")

    @staticmethod
    def _answer_value(editor: QLineEdit | QComboBox) -> str:
        if isinstance(editor, QComboBox):
            return editor.currentText()
        return editor.text()

    def _submit(self) -> None:
        answers: list[ConfirmationAnswer] = []
        for prompt in self.prompts:
            batch = self.batch_checks.get(prompt.confirmation_id)
            remember = self.remember_checks.get(prompt.confirmation_id)
            answers.append(
                ConfirmationAnswer(
                    confirmation_id=prompt.confirmation_id,
                    value=self._answer_value(self.answer_inputs[prompt.confirmation_id]),
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
