from pathlib import Path

from PySide6.QtCore import Qt

from core.knowledge.models import KnowledgeRecord, KnowledgeSourceKind
from core.knowledge.repository import KnowledgeRepository
from core.platform.paths import AppPaths
from core.security.credentials import InMemoryCredentialStore
from core.storage.settings import SettingsStore
from ui.pages.knowledge_page import KnowledgePage
from ui.pages.settings_page import SettingsPage


def test_settings_saves_key_to_credential_store_only(qtbot, database, tmp_path: Path) -> None:
    settings = SettingsStore(database)
    credentials = InMemoryCredentialStore()
    page = SettingsPage(settings, AppPaths.for_root(tmp_path / "settings"), credentials)
    qtbot.addWidget(page)
    page.provider_combo.setCurrentText("OpenAI兼容")
    page.base_url_edit.setText("https://example.invalid/v1")
    page.model_edit.setText("quality-model")
    page.api_key_edit.setText("secret-value")
    page.network_checkbox.setChecked(True)

    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert credentials.get_secret("openai-compatible") == "secret-value"
    assert page.api_key_edit.text() == ""
    assert page.credential_status_label.text() == "已安全保存"
    settings_dump = " ".join(
        str(row["value"]) for row in database.query_all("SELECT value FROM settings")
    )
    assert "secret-value" not in settings_dump
    assert settings.get("ai_provider") == "openai-compatible"
    assert settings.get("ai_network_enabled") == "true"


def test_settings_supports_deepseek_defaults_and_provider_scoped_key(
    qtbot, database, tmp_path: Path
) -> None:
    settings = SettingsStore(database)
    credentials = InMemoryCredentialStore()
    page = SettingsPage(settings, AppPaths.for_root(tmp_path / "deepseek"), credentials)
    qtbot.addWidget(page)

    page.provider_combo.setCurrentText("DeepSeek")
    assert page.base_url_edit.text() == "https://api.deepseek.com"
    assert page.model_edit.text() == "deepseek-v4-flash"
    page.api_key_edit.setText("deepseek-secret")
    page.network_checkbox.setChecked(True)
    qtbot.mouseClick(page.save_button, Qt.MouseButton.LeftButton)

    assert credentials.get_secret("deepseek") == "deepseek-secret"
    assert credentials.get_secret("openai-compatible") is None
    assert settings.get("ai_provider") == "deepseek"


def test_knowledge_page_searches_selected_namespace(qtbot, database, tmp_path: Path) -> None:
    repository = KnowledgeRepository(database)
    repository.add(
        KnowledgeRecord(
            "rule-1",
            "shared",
            "水分规则",
            "客户确认的水分判断标准",
            KnowledgeSourceKind.CONFIRMED_RULE,
            True,
        )
    )
    page = KnowledgePage(repository, tmp_path / "knowledge")
    qtbot.addWidget(page)
    page.namespace_combo.setCurrentText("公共知识")
    page.query_edit.setText("水分")

    qtbot.mouseClick(page.search_button, Qt.MouseButton.LeftButton)

    assert page.results.count() == 1
    assert "水分规则" in page.results.item(0).text()


def test_knowledge_import_copies_source_and_can_be_disabled(
    qtbot, database, tmp_path: Path
) -> None:
    repository = KnowledgeRepository(database)
    source = tmp_path / "历史案例.md"
    source.write_text("售后开裂案例，需要人工复核。", encoding="utf-8")
    page = KnowledgePage(repository, tmp_path / "knowledge")
    qtbot.addWidget(page)
    page.namespace_combo.setCurrentText("售后分析")
    page.enabled_checkbox.setChecked(True)

    record = page.import_file(source)

    copied = Path(record.source_path or "")
    assert copied.is_file()
    assert copied != source
    assert repository.search("after_sales", "开裂")[0].record_id == record.record_id

    item = next(
        page.records_list.item(index)
        for index in range(page.records_list.count())
        if page.records_list.item(index).data(256) == record.record_id
    )
    page.records_list.setCurrentItem(item)
    page.enabled_checkbox.setChecked(False)
    assert repository.search("after_sales", "开裂") == []
