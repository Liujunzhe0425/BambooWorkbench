from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from core.platform.paths import AppPaths
from core.security.credentials import CredentialStore
from core.storage.settings import SettingsStore

PROVIDERS = {
    "离线模拟": "mock",
    "OpenAI兼容": "openai-compatible",
}


class SettingsPage(QWidget):
    action_failed = Signal(str)

    def __init__(
        self,
        settings: SettingsStore,
        paths: AppPaths,
        credential_store: CredentialStore,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.paths = paths
        self.credential_store = credential_store
        self.setObjectName("page-settings")
        self.setAccessibleName("系统设置")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
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
        form.addRow("输出目录", self.output_dir_edit)

        self.provider_combo = QComboBox()
        self.provider_combo.setAccessibleName("AI提供商")
        for label, provider_id in PROVIDERS.items():
            self.provider_combo.addItem(label, provider_id)
        configured_provider = settings.get("ai_provider", "mock") or "mock"
        provider_index = self.provider_combo.findData(configured_provider)
        self.provider_combo.setCurrentIndex(max(provider_index, 0))
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

        self.network_checkbox = QCheckBox("允许在逐次确认后联网")
        self.network_checkbox.setAccessibleName("AI联网开关")
        self.network_checkbox.setChecked(settings.get("ai_network_enabled", "false") == "true")
        form.addRow("联网", self.network_checkbox)

        self.redaction_checkbox = QCheckBox("发送前必须显示脱敏预览")
        self.redaction_checkbox.setAccessibleName("脱敏确认开关")
        self.redaction_checkbox.setChecked(
            settings.get("ai_redaction_confirm", "true") != "false"
        )
        form.addRow("数据保护", self.redaction_checkbox)

        self.credential_status_label = QLabel(self._credential_status())
        self.credential_status_label.setAccessibleName("API密钥保存状态")
        form.addRow("密钥状态", self.credential_status_label)

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
        layout.addStretch()

    def save(self) -> None:
        provider_id = str(self.provider_combo.currentData())
        try:
            secret = self.api_key_edit.text()
            if secret:
                self.credential_store.set_secret("openai-compatible", secret)
            self.settings.set("output_dir", self.output_dir_edit.text().strip())
            self.settings.set("ai_provider", provider_id)
            self.settings.set("ai_base_url", self.base_url_edit.text().strip())
            self.settings.set("ai_model", self.model_edit.text().strip() or "mock-model")
            self.settings.set(
                "ai_network_enabled",
                "true" if self.network_checkbox.isChecked() else "false",
            )
            self.settings.set(
                "ai_redaction_confirm",
                "true" if self.redaction_checkbox.isChecked() else "false",
            )
        except Exception as error:
            self.action_failed.emit(f"设置保存失败：{error}")
            return
        self.api_key_edit.clear()
        self.credential_status_label.setText(
            "已安全保存" if self._has_credential() else "未保存（离线模拟不需要）"
        )

    def _has_credential(self) -> bool:
        try:
            return self.credential_store.has_secret("openai-compatible")
        except Exception:
            return False

    def _credential_status(self) -> str:
        return "已安全保存" if self._has_credential() else "未保存（离线模拟不需要）"

    def open_log_directory(self) -> None:
        try:
            self.paths.logs.mkdir(parents=True, exist_ok=True)
            opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.logs.resolve())))
        except Exception as error:
            self.action_failed.emit(str(error))
            return
        if not opened:
            self.action_failed.emit("系统未能打开日志目录")
