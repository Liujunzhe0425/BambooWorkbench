from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.ai.providers import (
    AIRequest,
    DeepSeekProvider,
    OpenAICompatibleProvider,
)
from core.security.credentials import CredentialStore
from core.storage.repositories.credential_state import CredentialStateRepository
from core.storage.settings import SettingsStore

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class AfterSalesAiSetupPage(QWidget):
    setup_completed = Signal()
    action_failed = Signal(str)

    def __init__(
        self,
        settings: SettingsStore,
        credentials: CredentialStore,
        reload_configuration: Callable[[], None],
        connection_tester: Callable[[str, str, str, str], None] | None = None,
        credential_state: CredentialStateRepository | None = None,
    ) -> None:
        super().__init__()
        self.settings = settings
        self.credentials = credentials
        self.reload_configuration = reload_configuration
        self.connection_tester = connection_tester or self._test_provider
        self.credential_state = credential_state
        self._verified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 24, 30, 28)
        layout.setSpacing(16)
        title = QLabel("售后 AI 接入")
        title.setProperty("pageTitle", True)
        subtitle = QLabel(
            "售后标准流程必须先完成框架托管的 AI 配置与连接测试。"
            "密钥只保存在 Windows 安全凭据中，不会交给售后模块。"
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("subtle", True)

        card = QFrame()
        card.setProperty("card", True)
        card_layout = QVBoxLayout(card)
        form = QFormLayout()
        self.provider_combo = QComboBox()
        self.provider_combo.addItem("DeepSeek", "deepseek")
        self.provider_combo.addItem("OpenAI 兼容接口", "openai-compatible")
        self.base_url_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("留空表示使用已安全保存的密钥")
        form.addRow("Provider", self.provider_combo)
        form.addRow("HTTPS Base URL", self.base_url_edit)
        form.addRow("模型", self.model_edit)
        form.addRow("API Key", self.api_key_edit)
        self.credential_status = QLabel("尚未检查凭据")
        self.connection_status = QLabel("请先测试连接")
        self.test_button = QPushButton("测试连接")
        self.test_button.setProperty("secondary", True)
        self.continue_button = QPushButton("继续选择 Excel")
        self.continue_button.setProperty("primary", True)
        self.continue_button.setEnabled(False)
        card_layout.addLayout(form)
        card_layout.addWidget(self.credential_status)
        card_layout.addWidget(self.connection_status)
        card_layout.addWidget(self.test_button)
        card_layout.addWidget(self.continue_button)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(card)
        layout.addStretch()

        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        self.base_url_edit.textChanged.connect(self._invalidate)
        self.model_edit.textChanged.connect(self._invalidate)
        self.api_key_edit.textChanged.connect(self._invalidate)
        self.test_button.clicked.connect(self.test_connection)
        self.continue_button.clicked.connect(self._continue)

    @property
    def verified(self) -> bool:
        return self._verified

    def activate(self) -> None:
        provider = self.settings.get("ai_provider", "deepseek") or "deepseek"
        index = self.provider_combo.findData(provider)
        self.provider_combo.setCurrentIndex(max(index, 0))
        self.base_url_edit.setText(
            self.settings.get("ai_base_url", "") or self._default_base_url(provider)
        )
        self.model_edit.setText(
            self.settings.get("ai_model", "")
            or ("deepseek-chat" if provider == "deepseek" else "gpt-4.1-mini")
        )
        self.api_key_edit.clear()
        self._verified = False
        self.continue_button.setEnabled(False)
        try:
            secret = self.credentials.get_secret(provider)
        except Exception:
            secret = None
        self.credential_status.setText(
            f"已配置密钥：••••{secret[-4:]}" if secret else "尚未配置密钥"
        )
        self.connection_status.setText("请确认配置并测试连接")

    def test_connection(self) -> None:
        provider = str(self.provider_combo.currentData())
        base_url = self.base_url_edit.text().strip().rstrip("/")
        model = self.model_edit.text().strip()
        key = self.api_key_edit.text().strip()
        if not base_url.startswith("https://"):
            self.action_failed.emit("售后 AI Base URL 必须使用 HTTPS")
            return
        if not _MODEL.fullmatch(model):
            self.action_failed.emit("售后 AI 模型名称无效")
            return
        if not key:
            try:
                key = self.credentials.get_secret(provider) or ""
            except Exception:
                key = ""
        if not key:
            self.action_failed.emit("请先输入 API Key")
            return
        self.test_button.setEnabled(False)
        self.connection_status.setText("正在由框架测试连接…")
        try:
            self.connection_tester(provider, base_url, model, key)
            had_same_secret = False
            with suppress(Exception):
                had_same_secret = self.credentials.get_secret(provider) == key
            self.credentials.set_secret(provider, key)
            if self.credential_state is not None and (
                not had_same_secret or self.credential_state.revision(provider) is None
            ):
                self.credential_state.rotate_revision(provider)
            self.settings.set("ai_provider", provider)
            self.settings.set("ai_base_url", base_url)
            self.settings.set("ai_model", model)
            if self.credential_state is not None:
                self.credential_state.mark_verified(provider, base_url, model)
            self.reload_configuration()
        except Exception as error:
            self._verified = False
            self.continue_button.setEnabled(False)
            self.connection_status.setText("连接测试失败")
            self.action_failed.emit(f"售后 AI 连接测试失败：{type(error).__name__}")
        else:
            self.api_key_edit.clear()
            self._verified = True
            self.credential_status.setText(f"已配置密钥：••••{key[-4:]}")
            self.connection_status.setText("连接测试通过，可继续选择 Excel")
            self.continue_button.setEnabled(True)
        finally:
            self.test_button.setEnabled(True)

    def _provider_changed(self) -> None:
        provider = str(self.provider_combo.currentData())
        self.base_url_edit.setText(self._default_base_url(provider))
        self._invalidate()

    def _invalidate(self) -> None:
        self._verified = False
        self.continue_button.setEnabled(False)
        self.connection_status.setText("配置已变化，请重新测试连接")

    def _continue(self) -> None:
        if self._verified:
            self.setup_completed.emit()

    def configuration_is_verified(self) -> bool:
        provider = self.settings.get("ai_provider", "") or ""
        base_url = self.settings.get("ai_base_url", "") or ""
        model = self.settings.get("ai_model", "") or ""
        if not provider or not base_url or not model or provider == "mock":
            return False
        try:
            if not self.credentials.has_secret(provider):
                return False
        except Exception:
            return False
        return bool(
            self.credential_state
            and self.credential_state.is_verified(provider, base_url, model)
        )

    @staticmethod
    def _default_base_url(provider: str) -> str:
        return "https://api.deepseek.com" if provider == "deepseek" else "https://api.openai.com/v1"

    @staticmethod
    def _test_provider(provider: str, base_url: str, model: str, key: str) -> None:
        configured = (
            DeepSeekProvider(key, base_url)
            if provider == "deepseek"
            else OpenAICompatibleProvider(base_url, key)
        )
        configured.complete(
            AIRequest(
                model=model,
                system="你是连接测试助手。",
                prompt="仅回复 OK。",
                response_format="text",
            )
        )
