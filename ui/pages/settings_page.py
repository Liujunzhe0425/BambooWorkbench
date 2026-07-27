from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from core.platform.paths import AppPaths
from core.security.credentials import CredentialStore
from core.storage.repositories.credential_state import CredentialStateRepository
from core.storage.repositories.output_roots import OutputRootRepository
from core.storage.settings import SettingsStore

PROVIDERS = {
    "离线模拟": "mock",
    "DeepSeek": "deepseek",
    "OpenAI兼容": "openai-compatible",
}

PROVIDER_DEFAULTS = {
    "mock": ("", "mock-model"),
    "deepseek": ("https://api.deepseek.com", "deepseek-v4-flash"),
    "openai-compatible": ("https://api.openai.com/v1", ""),
}


class SettingsPage(QWidget):
    action_failed = Signal(str)
    settings_saved = Signal()
    check_updates_requested = Signal()

    def __init__(
        self,
        settings: SettingsStore,
        paths: AppPaths,
        credential_store: CredentialStore,
        credential_state: CredentialStateRepository | None = None,
        output_roots: OutputRootRepository | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.paths = paths
        self.credential_store = credential_store
        self.credential_state = credential_state
        self.output_roots = output_roots
        self.setObjectName("page-settings")
        self.setAccessibleName("系统设置")

        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(30, 24, 30, 28)
        page_layout.setSpacing(0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("settingsScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("settingsScrollContent")
        layout = QVBoxLayout(self.scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        title = QLabel("系统设置")
        title.setProperty("pageTitle", True)
        subtitle = QLabel("管理本地输出、AI 接口与数据保护选项。设置只保存在当前电脑。")
        subtitle.setProperty("subtle", True)
        settings_card = QFrame()
        settings_card.setProperty("card", True)
        card_layout = QVBoxLayout(settings_card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(16)
        section = QLabel("基础配置")
        section.setProperty("section", True)
        form = QFormLayout()
        form.setHorizontalSpacing(24)
        form.setVerticalSpacing(13)

        self.output_dir_edit = QLineEdit(settings.get("output_dir", "") or "")
        self.output_dir_edit.setAccessibleName("输出目录")
        self.output_dir_edit.setPlaceholderText(str(paths.output))
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(8)
        self.output_browse_button = QPushButton("选择…")
        self.output_browse_button.setProperty("secondary", True)
        self.output_browse_button.clicked.connect(self._choose_output_directory)
        output_layout.addWidget(self.output_dir_edit, 1)
        output_layout.addWidget(self.output_browse_button)
        form.addRow("输出目录", output_row)
        output_hint = QLabel(
            "默认保存在安装根目录的 output；修改后只影响新成果的根目录，"
            "任务名称和时间构成的独立文件夹结构保持不变。"
        )
        output_hint.setWordWrap(True)
        output_hint.setProperty("caption", True)
        form.addRow("", output_hint)

        self.provider_combo = QComboBox()
        self.provider_combo.setAccessibleName("AI提供商")
        for label, provider_id in PROVIDERS.items():
            self.provider_combo.addItem(label, provider_id)
        configured_provider = settings.get("ai_provider", "mock") or "mock"
        provider_index = self.provider_combo.findData(configured_provider)
        self.provider_combo.setCurrentIndex(max(provider_index, 0))
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        form.addRow("AI提供商", self.provider_combo)

        self.base_url_edit = QLineEdit(
            settings.get("ai_base_url", "https://api.openai.com/v1")
            or "https://api.openai.com/v1"
        )
        self.base_url_edit.setAccessibleName("AI接口地址")
        form.addRow("API地址", self.base_url_edit)

        self.model_edit = QLineEdit(settings.get("ai_model", "mock-model") or "mock-model")
        self.model_edit.setAccessibleName("AI模型")
        form.addRow("模型", self.model_edit)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setAccessibleName("API密钥")
        self.api_key_edit.setPlaceholderText("仅保存到 Windows 安全凭据")
        form.addRow("API密钥", self.api_key_edit)

        self.network_checkbox = QCheckBox("默认允许 AI 联网")
        self.network_checkbox.setAccessibleName("AI联网开关")
        self.network_checkbox.setChecked(settings.get("ai_network_enabled", "false") == "true")
        form.addRow("联网", self.network_checkbox)

        self.redaction_checkbox = QCheckBox("始终执行脱敏并记录授权审计（不可关闭）")
        self.redaction_checkbox.setAccessibleName("强制脱敏与授权审计")
        self.redaction_checkbox.setChecked(True)
        self.redaction_checkbox.setEnabled(False)
        form.addRow("数据保护", self.redaction_checkbox)

        self.credential_status_label = QLabel(self._credential_status())
        self.credential_status_label.setAccessibleName("API密钥保存状态")
        form.addRow("密钥状态", self.credential_status_label)
        self.delete_ai_key_button = QPushButton("删除当前 Provider 密钥")
        self.delete_ai_key_button.setProperty("secondary", True)
        self.delete_ai_key_button.clicked.connect(self.delete_current_provider_key)
        form.addRow("密钥管理", self.delete_ai_key_button)

        self.version_label = QLabel(__version__)
        self.version_label.setAccessibleName("软件版本")
        form.addRow("版本", self.version_label)

        self.save_button = QPushButton("保存设置")
        self.save_button.setProperty("primary", True)
        self.save_button.setAccessibleName("保存系统设置")
        self.save_button.clicked.connect(self.save)
        self.open_logs_button = QPushButton("打开日志目录")
        self.open_logs_button.setAccessibleName("打开应用日志目录")
        self.open_logs_button.clicked.connect(self.open_log_directory)
        self.open_logs_button.setProperty("secondary", True)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(self.open_logs_button)
        actions.addWidget(self.save_button)
        card_layout.addWidget(section)
        card_layout.addLayout(form)
        card_layout.addLayout(actions)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(settings_card)

        update_card = QFrame()
        update_card.setProperty("card", True)
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(22, 20, 22, 20)
        update_layout.setSpacing(12)
        update_title = QLabel("软件更新")
        update_title.setProperty("section", True)
        update_hint = QLabel(
            "安装版启动后可匿名检查公开二进制 Release；无需 GitHub 令牌。"
            "只有确认更新时才下载。"
            "检查失败不会影响离线数据处理。"
        )
        update_hint.setWordWrap(True)
        update_hint.setProperty("caption", True)
        self.auto_update_checkbox = QCheckBox("启动后自动检查更新")
        self.auto_update_checkbox.setChecked(
            settings.get("update_auto_check", "true") == "true"
        )
        self.auto_update_checkbox.setAccessibleName("自动检查软件更新")
        update_form = QFormLayout()
        update_form.setHorizontalSpacing(24)
        update_form.setVerticalSpacing(13)
        self.update_token_edit = QLineEdit()
        self.update_token_edit.setVisible(False)
        self.update_token_edit.setEnabled(False)
        self.update_credential_label = QLabel(self._update_credential_status())
        self.update_credential_label.setAccessibleName("公开更新源访问状态")
        update_form.addRow("更新源", self.update_credential_label)
        self.delete_update_token_button = QPushButton("删除旧版 GitHub 更新令牌")
        self.delete_update_token_button.setProperty("secondary", True)
        self.delete_update_token_button.clicked.connect(self.delete_update_token)
        update_form.addRow("旧版凭据", self.delete_update_token_button)
        private_hint = QLabel(
            "自动更新只访问独立的公开二进制分发仓库；私有源码、客户数据和密钥不会公开。"
            "旧版本保存过的更新令牌不再使用，可在此安全删除。"
        )
        private_hint.setWordWrap(True)
        private_hint.setProperty("caption", True)
        self.update_status_label = QLabel("尚未检查")
        self.update_status_label.setProperty("subtle", True)
        self.check_update_button = QPushButton("立即检查更新")
        self.check_update_button.setProperty("secondary", True)
        self.check_update_button.clicked.connect(self.check_updates_requested)
        update_actions = QHBoxLayout()
        update_actions.addWidget(self.update_status_label)
        update_actions.addStretch()
        update_actions.addWidget(self.check_update_button)
        update_layout.addWidget(update_title)
        update_layout.addWidget(update_hint)
        update_layout.addWidget(self.auto_update_checkbox)
        update_layout.addLayout(update_form)
        update_layout.addWidget(private_hint)
        update_layout.addLayout(update_actions)
        layout.addWidget(update_card)
        layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        page_layout.addWidget(self.scroll_area)

    def save(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        try:
            secret = self.api_key_edit.text()
            if secret and provider_id != "mock":
                self.credential_store.set_secret(provider_id, secret)
                if self.credential_state is not None:
                    self.credential_state.rotate_revision(provider_id)
            output_directory = self.output_dir_edit.text().strip() or str(self.paths.output)
            if self.output_roots is not None:
                self.output_roots.set_current(
                    Path(output_directory),
                    is_default=Path(output_directory).resolve() == self.paths.output,
                )
            self.settings.set("output_dir", output_directory)
            self.settings.set("ai_provider", provider_id)
            self.settings.set("ai_base_url", self.base_url_edit.text().strip())
            self.settings.set("ai_model", self.model_edit.text().strip() or "mock-model")
            self.settings.set(
                "ai_network_enabled",
                "true" if self.network_checkbox.isChecked() else "false",
            )
            self.settings.set(
                "ai_redaction_confirm",
                "true",
            )
            self.settings.set(
                "update_auto_check",
                "true" if self.auto_update_checkbox.isChecked() else "false",
            )
        except Exception as error:
            self.action_failed.emit(f"设置保存失败：{error}")
            return
        self.api_key_edit.clear()
        self.update_token_edit.clear()
        self.credential_status_label.setText(self._credential_status())
        self.update_credential_label.setText(self._update_credential_status())
        self.settings_saved.emit()

    def delete_current_provider_key(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        if provider_id == "mock":
            self.action_failed.emit("离线模拟 Provider 没有可删除的 API 密钥")
            return
        try:
            self.credential_store.delete_secret(provider_id)
            if self.credential_state is not None:
                self.credential_state.invalidate(provider_id)
        except Exception as error:
            self.action_failed.emit(f"删除 AI 密钥失败：{error}")
            return
        self.api_key_edit.clear()
        self.credential_status_label.setText(self._credential_status())
        self.settings_saved.emit()

    def delete_update_token(self) -> None:
        try:
            self.credential_store.delete_secret("github-updates")
        except Exception as error:
            self.action_failed.emit(f"删除更新令牌失败：{error}")
            return
        self.update_token_edit.clear()
        self.update_credential_label.setText(self._update_credential_status())

    def set_update_status(self, message: str) -> None:
        self.update_status_label.setText(message)

    def _update_credential_status(self) -> str:
        try:
            saved = self.credential_store.has_secret("github-updates")
        except Exception:
            saved = False
        return "公开源无需令牌；检测到旧版令牌" if saved else "公开源无需令牌"

    def _has_credential(self) -> bool:
        provider_id = str(self.provider_combo.currentData())
        if provider_id == "mock":
            return False
        try:
            return self.credential_store.has_secret(provider_id)
        except Exception:
            return False

    def _credential_status(self) -> str:
        provider_id = str(self.provider_combo.currentData())
        if provider_id == "mock":
            return "未保存（离线模拟不需要）"
        return "已安全保存" if self._has_credential() else "未保存"

    def _provider_changed(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        default_base_url, default_model = PROVIDER_DEFAULTS[provider_id]
        self.base_url_edit.setText(default_base_url)
        self.model_edit.setText(default_model)
        self.credential_status_label.setText(self._credential_status())

    def _choose_output_directory(self) -> None:
        initial = self.output_dir_edit.text().strip() or str(self.paths.root)
        selected = QFileDialog.getExistingDirectory(self, "选择成果输出目录", initial)
        if selected:
            self.output_dir_edit.setText(selected)

    def open_log_directory(self) -> None:
        try:
            self.paths.logs.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.logs.resolve())))
        except Exception as error:
            self.action_failed.emit(str(error))
            return
        if not opened:
            self.action_failed.emit("系统未能打开日志目录")
