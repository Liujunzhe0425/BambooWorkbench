import json
import shutil
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.knowledge.learning import LearningEvidenceRepository
from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository

NAMESPACE_LABELS = {
    "公共知识": "shared",
    "竹丝水分": "moisture",
    "水煮实验": "boiling",
    "售后分析": "after_sales",
}
TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}


class KnowledgePage(QWidget):
    action_failed = Signal(str)
    namespaces = ("shared", "moisture", "boiling", "after_sales")
    message = "本地知识元数据与确定性检索已启用；当前版本不包含向量检索"

    def __init__(
        self,
        repository: KnowledgeRepository | None = None,
        knowledge_root: Path | None = None,
        learning_repository: LearningEvidenceRepository | None = None,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.knowledge_root = knowledge_root
        self.learning_repository = learning_repository
        self._updating_enabled = False
        self.setObjectName("page-knowledge")
        self.setAccessibleName("知识库")

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(30, 24, 30, 28)
        page_layout.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("knowledgeScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("knowledgeScrollContent")
        layout = QVBoxLayout(self.scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        title = QLabel("知识库")
        title.setProperty("pageTitle", True)
        self.message_label = QLabel(self.message)
        self.message_label.setProperty("subtle", True)
        self.message_label.setAccessibleName("知识库接入状态")

        search_card = QFrame()
        search_card.setProperty("card", True)
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(20, 17, 20, 18)
        search_layout.setSpacing(11)
        search_title = QLabel("确定性知识检索")
        search_title.setProperty("section", True)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        self.namespace_combo = QComboBox()
        self.namespace_combo.setAccessibleName("知识库检索命名空间")
        for label, namespace in NAMESPACE_LABELS.items():
            self.namespace_combo.addItem(label, namespace)
        self.query_edit = QLineEdit()
        self.query_edit.setAccessibleName("知识检索关键词")
        self.query_edit.setPlaceholderText("输入规则、字段或案例关键词")
        self.search_button = QPushButton("检索")
        self.search_button.setProperty("primary", True)
        self.search_button.setAccessibleName("检索本地知识")
        self.search_button.clicked.connect(self.search)
        form.addRow("知识域", self.namespace_combo)
        form.addRow("关键词", self.query_edit)

        self.results = QListWidget()
        self.results.setAccessibleName("知识检索结果")
        self.import_button = QPushButton("导入知识材料")
        self.import_button.setProperty("secondary", True)
        self.import_button.setAccessibleName("导入本地知识材料")
        self.import_button.clicked.connect(self._choose_import)
        self.records_list = QListWidget()
        self.records_list.setAccessibleName("已导入知识条目")
        self.records_list.currentItemChanged.connect(self._record_selected)
        self.enabled_checkbox = QCheckBox("启用选中知识条目")
        self.enabled_checkbox.setAccessibleName("知识条目启用状态")
        self.enabled_checkbox.setChecked(True)
        self.enabled_checkbox.toggled.connect(self._enabled_changed)

        # Kept as an explicit compatibility/diagnostic list for module namespace tests.
        self.namespace_list = QListWidget()
        self.namespace_list.setAccessibleName("知识库命名空间")
        self.namespace_list.addItems(self.namespaces)
        self.namespace_list.hide()

        layout.addWidget(title)
        layout.addWidget(self.message_label)
        search_layout.addWidget(search_title)
        search_layout.addLayout(form)
        search_layout.addWidget(self.search_button)
        layout.addWidget(search_card)

        columns = QGridLayout()
        columns.setHorizontalSpacing(14)
        results_card = QFrame()
        results_card.setProperty("card", True)
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(18, 16, 18, 18)
        results_title = QLabel("检索结果")
        results_title.setProperty("section", True)
        results_layout.addWidget(results_title)
        results_layout.addWidget(self.results, 1)

        records_card = QFrame()
        records_card.setProperty("card", True)
        records_layout = QVBoxLayout(records_card)
        records_layout.setContentsMargins(18, 16, 18, 18)
        records_header = QHBoxLayout()
        records_title = QLabel("知识条目")
        records_title.setProperty("section", True)
        records_header.addWidget(records_title)
        records_header.addStretch()
        records_header.addWidget(self.import_button)
        records_layout.addLayout(records_header)
        records_layout.addWidget(self.records_list, 1)
        records_layout.addWidget(self.enabled_checkbox)
        columns.addWidget(results_card, 0, 0)
        columns.addWidget(records_card, 0, 1)
        columns.setColumnStretch(0, 1)
        columns.setColumnStretch(1, 1)
        layout.addLayout(columns, 1)
        learning_card = QFrame()
        learning_card.setProperty("card", True)
        learning_layout = QVBoxLayout(learning_card)
        learning_header = QHBoxLayout()
        learning_title = QLabel("用户偏好证据")
        learning_title.setProperty("section", True)
        self.learning_module_combo = QComboBox()
        for label, namespace in NAMESPACE_LABELS.items():
            if namespace != "shared":
                self.learning_module_combo.addItem(label, namespace)
        self.learning_module_combo.currentIndexChanged.connect(self.refresh_learning)
        learning_header.addWidget(learning_title)
        learning_header.addStretch()
        learning_header.addWidget(self.learning_module_combo)
        self.learning_list = QListWidget()
        self.learning_list.setAccessibleName("知识自学习证据")
        self.revoke_evidence_button = QPushButton("撤销选中任务证据")
        self.reset_scenario_button = QPushButton("重置选中学习场景")
        self.reset_module_button = QPushButton("重置当前模块全部偏好")
        for button in (
            self.revoke_evidence_button,
            self.reset_scenario_button,
            self.reset_module_button,
        ):
            button.setProperty("secondary", True)
        self.revoke_evidence_button.clicked.connect(self._revoke_selected_evidence)
        self.reset_scenario_button.clicked.connect(self._reset_selected_scenario)
        self.reset_module_button.clicked.connect(self._reset_learning_module)
        learning_actions = QHBoxLayout()
        learning_actions.addWidget(self.revoke_evidence_button)
        learning_actions.addWidget(self.reset_scenario_button)
        learning_actions.addWidget(self.reset_module_button)
        learning_layout.addLayout(learning_header)
        learning_layout.addWidget(
            QLabel("权重只调整确认页建议值，不会修改已批准规则、公式或阈值。")
        )
        learning_layout.addWidget(self.learning_list)
        learning_layout.addLayout(learning_actions)
        layout.addWidget(learning_card)
        self.scroll_area.setWidget(self.scroll_content)
        page_layout.addWidget(self.scroll_area)
        self.refresh_records()
        self.refresh_learning()

    def lookup(self, namespace: str, query: str) -> list[KnowledgeRecord]:
        if namespace not in self.namespaces:
            raise ValueError(f"unknown knowledge namespace: {namespace}")
        if self.repository is None:
            return []
        return self.repository.search(namespace, query)

    def search(self) -> None:
        namespace = str(self.namespace_combo.currentData())
        try:
            matches = self.lookup(namespace, self.query_edit.text())
        except Exception as error:
            self.action_failed.emit(f"知识检索失败：{error}")
            return
        self.results.clear()
        if not matches:
            self.results.addItem("未找到匹配条目")
            return
        for record in matches:
            self.results.addItem(
                f"[{record.source_kind.value}] {record.title}（{record.namespace}）"
            )

    def import_file(self, source: Path) -> KnowledgeRecord:
        if self.repository is None or self.knowledge_root is None:
            raise RuntimeError("knowledge import service is unavailable")
        source = source.resolve(strict=True)
        if not source.is_file():
            raise ValueError("knowledge source must be a file")
        imports = (self.knowledge_root / "imports").resolve()
        imports.mkdir(parents=True, exist_ok=True)
        target = (imports / f"{uuid4().hex}{source.suffix.lower()}").resolve()
        if not target.is_relative_to(imports):
            raise ValueError("knowledge import target escaped its root")
        shutil.copy2(source, target)
        try:
            content = self._extract_content(source)
            record = KnowledgeRecord(
                record_id=f"import-{uuid4().hex}",
                namespace=str(self.namespace_combo.currentData()),
                title=source.stem,
                content=content,
                source_kind=KnowledgeSourceKind.HISTORICAL_EXAMPLE,
                enabled=self.enabled_checkbox.isChecked(),
                source_path=str(target),
            )
            self.repository.add(record)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        self.refresh_records()
        return record

    def refresh_records(self) -> None:
        self.records_list.clear()
        if self.repository is None:
            self.enabled_checkbox.setEnabled(False)
            return
        self.enabled_checkbox.setEnabled(True)
        for record in self.repository.list_records():
            state = "启用" if record.enabled else "停用"
            item = QListWidgetItem(f"{record.title}（{record.namespace}，{state}）")
            item.setData(256, record.record_id)
            item.setData(257, record.enabled)
            self.records_list.addItem(item)

    def _choose_import(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "选择知识材料",
            "",
            "知识材料 (*.txt *.md *.csv *.json *.yaml *.yml *.xlsx *.docx);;所有文件 (*)",
        )
        if not filename:
            return
        try:
            self.import_file(Path(filename))
        except Exception as error:
            self.action_failed.emit(f"知识导入失败：{error}")

    def _record_selected(self, current: QListWidgetItem | None) -> None:
        self._updating_enabled = True
        try:
            self.enabled_checkbox.setChecked(bool(current and current.data(257)))
        finally:
            self._updating_enabled = False

    def _enabled_changed(self, enabled: bool) -> None:
        if self._updating_enabled or self.repository is None:
            return
        current = self.records_list.currentItem()
        if current is None:
            return
        try:
            self.repository.set_enabled(str(current.data(256)), enabled)
            self.refresh_records()
        except Exception as error:
            self.action_failed.emit(f"知识状态更新失败：{error}")

    def refresh_learning(self) -> None:
        self.learning_list.clear()
        enabled = self.learning_repository is not None
        for button in (
            self.revoke_evidence_button,
            self.reset_scenario_button,
            self.reset_module_button,
        ):
            button.setEnabled(enabled)
        if not enabled:
            self.learning_list.addItem("自学习仓储不可用")
            return
        module_id = str(self.learning_module_combo.currentData())
        for record in self.learning_repository.list_module(module_id):
            state = "有效" if record["active"] else "已撤销"
            item = QListWidgetItem(
                f"{record['learning_key']} · {record['candidate_label']} "
                f"(+{record['weight']}) · {record['year']}年{int(record['month']):02d}月 · {state}"
            )
            item.setData(256, record["evidence_id"])
            item.setData(257, record["learning_key"])
            item.setData(258, bool(record["active"]))
            item.setToolTip(
                f"来源任务：{record['job_id']}\n上下文："
                + json.dumps(record["context"], ensure_ascii=False, sort_keys=True)
            )
            self.learning_list.addItem(item)

    def _revoke_selected_evidence(self) -> None:
        current = self.learning_list.currentItem()
        if current is None or not current.data(258) or self.learning_repository is None:
            return
        if not self._confirm_learning_action("撤销这条任务证据？"):
            return
        self.learning_repository.revoke_evidence(
            str(current.data(256)), "user revoked evidence"
        )
        self.refresh_learning()

    def _reset_selected_scenario(self) -> None:
        current = self.learning_list.currentItem()
        if current is None or self.learning_repository is None:
            return
        if not self._confirm_learning_action("重置当前学习场景的全部偏好证据？"):
            return
        self.learning_repository.reset_scenario(
            str(self.learning_module_combo.currentData()),
            str(current.data(257)),
            "user reset scenario",
        )
        self.refresh_learning()

    def _reset_learning_module(self) -> None:
        if self.learning_repository is None or not self._confirm_learning_action(
            "重置当前模块全部自学习偏好？"
        ):
            return
        self.learning_repository.reset_module(
            str(self.learning_module_combo.currentData()), "user reset module"
        )
        self.refresh_learning()

    def _confirm_learning_action(self, question: str) -> bool:
        return (
            QMessageBox.question(
                self,
                "确认知识偏好操作",
                question + "\n该操作不会修改已批准规则。",
            )
            == QMessageBox.StandardButton.Yes
        )

    @staticmethod
    def _extract_content(source: Path) -> str:
        if source.suffix.lower() in TEXT_SUFFIXES:
            try:
                return source.read_text(encoding="utf-8")[:20_000]
            except UnicodeDecodeError:
                return f"导入文件：{source.name}；大小：{source.stat().st_size} 字节"
        return f"导入文件：{source.name}；大小：{source.stat().st_size} 字节"
