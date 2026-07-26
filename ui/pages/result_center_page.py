from pathlib import Path

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.contracts.enums import TaskStatus
from core.contracts.result import ModuleResult
from core.tasks.result_status import normalized_result
from ui.widgets.output_files import OutputFilesWidget

_STATUS_NAMES = {
    TaskStatus.SUCCESS: "已完成",
    TaskStatus.PARTIAL_SUCCESS: "部分完成",
    TaskStatus.FAILED: "失败",
    TaskStatus.CANCELLED: "已取消",
    TaskStatus.NEEDS_CONFIRMATION: "待确认",
}


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
        self.ai_notice = QLabel()
        self.ai_notice.setWordWrap(True)
        self.ai_notice.setProperty("subtle", True)
        self.ai_notice.setVisible(False)
        self.ai_audit_label = QLabel()
        self.ai_audit_label.setWordWrap(True)
        self.ai_audit_label.setProperty("caption", True)
        self.ai_audit_label.setVisible(False)
        self.failure_toggle = QToolButton()
        self.failure_toggle.setCheckable(True)
        self.failure_toggle.setProperty("detailToggle", True)
        self.failure_toggle.setVisible(False)
        self.failure_panel = QFrame()
        self.failure_panel.setProperty("failureDetails", True)
        self.failure_layout = QVBoxLayout(self.failure_panel)
        self.failure_layout.setContentsMargins(12, 8, 12, 8)
        self.failure_panel.setVisible(False)
        self.failure_toggle.toggled.connect(self._toggle_failures)
        self._failure_count = 0
        self.output_files = OutputFilesWidget()
        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)
        self.status_label.setProperty("section", True)
        card_layout.addWidget(self.status_label)
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 0, 0, 0)
        summary_row.addWidget(self.summary_label)
        summary_row.addStretch()
        summary_row.addWidget(self.failure_toggle)
        card_layout.addLayout(summary_row)
        card_layout.addWidget(self.failure_panel)
        card_layout.addWidget(self.ai_notice)
        card_layout.addWidget(self.ai_audit_label)
        card_layout.addWidget(self.output_files)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch()

    @property
    def output_buttons(self) -> list[QPushButton]:
        return self.output_files.buttons

    def show_result(self, result: ModuleResult) -> None:
        result = normalized_result(result)
        self.current_result = result
        status_name = _STATUS_NAMES.get(result.status, result.status.value)
        self.status_label.setText(f"任务状态：{status_name}")
        self.summary_label.setText(
            f"输入 {result.summary.input_count}，"
            f"已处理 {result.summary.processed_count}"
        )
        self._set_failures(result)
        self._set_ai_notice(result)
        self.output_files.set_outputs(result.outputs)

    def set_ai_audit(self, decisions: list[object]) -> None:
        if not decisions:
            self.ai_audit_label.clear()
            self.ai_audit_label.setVisible(False)
            return
        lines = []
        for decision in decisions:
            categories = "、".join(getattr(decision, "data_categories", ())) or "无"
            allowed = "允许" if bool(getattr(decision, "allowed", False)) else "拒绝"
            lines.append(
                f"{allowed} · 数据类别：{categories} · Provider："
                f"{getattr(decision, 'provider_id', 'unknown')} · 授权来源："
                f"{getattr(decision, 'authorization_source', 'legacy')}"
            )
        self.ai_audit_label.setText("本次 AI 授权与脱敏摘要：\n" + "\n".join(lines))
        self.ai_audit_label.setVisible(True)

    def _set_ai_notice(self, result: ModuleResult) -> None:
        notices = [error for error in result.errors if error.startswith("AI_REPORT_DEGRADED:")]
        if notices:
            reason = notices[0].split(":", 1)[1].strip()
            descriptions = {
                "provider_denied": "本次未授权联网，未生成 AI 报告。",
                "provider_error": "AI 服务暂不可用，已保留结构化降级记录，未生成虚假报告。",
                "provider_timeout": "AI 服务响应超时，已保留结构化降级记录，未生成虚假报告。",
                "invalid_ai_response": "AI 返回内容不符合报告契约，已保留结构化降级记录。",
            }
            self.ai_notice.setText(descriptions.get(reason, "AI 报告已安全降级，未生成虚假结论。"))
            self.ai_notice.setVisible(True)
            return
        generated = any(
            "ai_analysis_report" in Path(output.path).stem.casefold()
            for output in result.outputs
        )
        self.ai_notice.setText("AI 辅助报告已生成；业务规则和人工复核结论仍具有更高优先级。")
        self.ai_notice.setVisible(generated)

    def _set_failures(self, result: ModuleResult) -> None:
        while self.failure_layout.count():
            item = self.failure_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        failed = [
            item
            for item in result.file_results
            if item.status is TaskStatus.FAILED
        ]
        count = max(result.summary.failed_count, len(failed))
        self._failure_count = count
        self.failure_toggle.setChecked(False)
        self.failure_panel.setVisible(False)
        self.failure_toggle.setVisible(count > 0)
        self.failure_toggle.setText(f"▶  失败 {count}（点击查看）")
        if not count:
            return
        if failed:
            for item in failed:
                name = Path(item.source_file).name or "未命名文件"
                label = QLabel(f"• {name}：{_public_failure_reason(item.error)}")
                label.setWordWrap(True)
                self.failure_layout.addWidget(label)
        else:
            label = QLabel("• 模块报告存在处理失败，但未提供具体文件原因。")
            label.setWordWrap(True)
            self.failure_layout.addWidget(label)

    def _toggle_failures(self, expanded: bool) -> None:
        self.failure_panel.setVisible(expanded)
        self.failure_toggle.setText(
            f"{'▼' if expanded else '▶'}  失败 {self._failure_count}"
            f"（{'收起' if expanded else '点击查看'}）"
        )


def _public_failure_reason(error: str | None) -> str:
    text = (error or "").lower()
    if any(token in text for token in ("corrupt", "badzip", "损坏", "not a zip")):
        return "文件可能已损坏，无法作为有效 Excel 读取"
    if any(token in text for token in ("template", "header", "worksheet", "sheet", "结构", "表头")):
        return "文件模板或表格结构与当前模块要求不一致"
    unsupported_tokens = ("extension", "unsupported", "suffix", "文件类型", "格式不支持")
    if any(token in text for token in unsupported_tokens):
        return "文件类型不受当前模块支持"
    if any(token in text for token in ("permission", "denied", "locked", "读取", "read")):
        return "文件无法读取，请检查占用状态或访问权限"
    return "文件未能完成处理，请核对源文件格式后重试"
