import json
from contextlib import suppress
from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.contracts.result import OutputArtifact


class OutputFilesWidget(QWidget):
    open_failed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self.buttons: list[QPushButton] = []
        self.text_viewers: list[QDialog] = []

    def set_outputs(self, outputs: list[OutputArtifact]) -> None:
        self._clear()
        for artifact in outputs:
            path = self._existing_file(artifact.path)
            if path is None:
                continue
            is_json = artifact.mime_type == "application/json" or path.suffix.lower() == ".json"
            action = "查看" if is_json else "打开"
            suffix = "（业务明细）" if is_json else ""
            button = QPushButton(f"{action}{artifact.label}{suffix}")
            button.setAccessibleName(f"打开{artifact.label}")
            button.setAccessibleDescription(str(path))
            raw_path = Path(artifact.path)
            button.clicked.connect(
                lambda checked=False,
                target=raw_path,
                mime_type=artifact.mime_type,
                label=artifact.label: self._open_output(target, mime_type, label)
            )
            self.buttons.append(button)
            self._layout.addWidget(button)
        if not self.buttons:
            self._layout.addWidget(QLabel("没有可打开的输出文件"))
        self._layout.addStretch()

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.buttons.clear()

    @staticmethod
    def _existing_file(raw_path: str) -> Path | None:
        path = Path(raw_path)
        try:
            if path.is_symlink() or not path.is_file():
                return None
            return path.resolve(strict=True)
        except (OSError, RuntimeError):
            return None

    def _open_output(self, path: Path, mime_type: str = "", label: str = "") -> None:
        resolved = self._existing_file(str(path))
        if resolved is None:
            self.open_failed.emit("输出文件不可用，可能已移动、删除或被链接替换")
            return
        is_json = mime_type == "application/json" or resolved.suffix.lower() == ".json"
        if is_json:
            try:
                self._show_text_artifact(resolved, label)
                return
            except OSError as error:
                self.open_failed.emit(f"无法读取输出文件：{error}")
                return
        if QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved))):
            return
        if self._is_text_artifact(resolved, mime_type):
            try:
                self._show_text_artifact(resolved, label)
                return
            except OSError as error:
                self.open_failed.emit(f"无法读取输出文件：{error}")
                return
        self.open_failed.emit("系统未能打开输出文件，且该文件不支持内置预览")

    @staticmethod
    def _is_text_artifact(path: Path, mime_type: str) -> bool:
        return mime_type.startswith("text/") or mime_type in {
            "application/json",
            "application/yaml",
        } or path.suffix.lower() in {
            ".md",
            ".json",
            ".txt",
            ".csv",
            ".log",
            ".yaml",
            ".yml",
        }

    def _show_text_artifact(self, path: Path, label: str) -> None:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
        payload: object | None = None
        if path.suffix.lower() == ".json":
            with suppress(json.JSONDecodeError):
                payload = json.loads(content)
                content = json.dumps(payload, ensure_ascii=False, indent=2)
        viewer = QDialog(self)
        viewer.setWindowTitle(label or path.name)
        viewer.setModal(False)
        viewer.resize(860, 620)
        layout = QVBoxLayout(viewer)
        title = QLabel(f"{label or path.name} · {path.name}")
        title.setProperty("section", True)
        tabs = QTabWidget()
        if payload is not None:
            tabs.addTab(self._business_view(payload), "业务明细")
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(content)
        editor.setAccessibleName(f"{label or path.name}技术明细")
        tabs.addTab(editor, "技术 JSON" if payload is not None else "文件内容")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(viewer.close)
        layout.addWidget(title)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)
        self.text_viewers.append(viewer)
        viewer.finished.connect(
            lambda _result, dialog=viewer: self._remove_text_viewer(dialog)
        )
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    @staticmethod
    def _business_view(payload: object) -> QWidget:
        host = QWidget()
        layout = QVBoxLayout(host)
        layout.setContentsMargins(8, 8, 8, 8)
        records, group_name = _records_from_payload(payload)
        hint = QLabel(
            f"{group_name}：共 {len(records)} 条。这里只整理原始结构化字段，"
            "不新增或改写业务结论。"
        )
        hint.setWordWrap(True)
        hint.setProperty("subtle", True)
        layout.addWidget(hint)
        if not records:
            layout.addWidget(QLabel("当前文件没有可展示的业务记录。"))
            layout.addStretch()
            return host

        columns = _display_columns(records)
        table = QTableWidget(len(records), len(columns))
        table.setHorizontalHeaderLabels([_FIELD_LABELS.get(key, key) for key in columns])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        for row, record in enumerate(records):
            for column, key in enumerate(columns):
                item = QTableWidgetItem(_display_value(record.get(key)))
                table.setItem(row, column, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        layout.addWidget(table, 1)
        return host

    def _remove_text_viewer(self, viewer: QDialog) -> None:
        if viewer in self.text_viewers:
            self.text_viewers.remove(viewer)
        viewer.deleteLater()


_FIELD_LABELS = {
    "source_file": "来源文件",
    "sheet": "工作表",
    "case_id": "案件编号",
    "customer": "客户",
    "complaint_date": "投诉日期",
    "product": "产品",
    "spec": "规格",
    "issue_types": "问题分类",
    "primary_issue_type": "主要问题",
    "cost": "费用",
    "case_status": "案件状态",
    "needs_review": "需要复核",
    "sample_id": "样品编号",
    "product_usage": "产品用途",
    "density": "密度",
    "average_density": "平均密度",
    "expansion_ratio": "膨胀率",
    "average_expansion_ratio": "平均膨胀率",
    "grade": "等级",
    "status": "状态",
    "warnings": "提示",
}
_PREFERRED_COLUMNS = tuple(_FIELD_LABELS)


def _records_from_payload(payload: object) -> tuple[list[dict[str, object]], str]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)], "业务记录"
    if not isinstance(payload, dict):
        return [], "业务记录"
    for key in ("records", "items", "cases", "rows", "data", "included_records"):
        value = payload.get(key)
        if isinstance(value, list) and any(isinstance(item, dict) for item in value):
            return [item for item in value if isinstance(item, dict)], _FIELD_LABELS.get(key, key)
    return [payload], "业务记录"


def _display_columns(records: list[dict[str, object]]) -> list[str]:
    available = {key for record in records for key in record}
    preferred = [key for key in _PREFERRED_COLUMNS if key in available]
    if preferred:
        return preferred[:12]
    scalar = [
        key
        for key in records[0]
        if any(not isinstance(record.get(key), (dict, list)) for record in records)
    ]
    return scalar[:12]


def _display_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        return "、".join(_display_value(item) for item in value) or "—"
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)
