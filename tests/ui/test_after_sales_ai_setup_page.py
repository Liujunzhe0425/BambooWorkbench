from core.security.credentials import InMemoryCredentialStore
from ui.pages.after_sales_ai_setup_page import AfterSalesAiSetupPage
from ui.pages.module_task_page import ModuleTaskPage


class _Settings:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def set(self, key: str, value: str) -> None:
        self.values[key] = value


def test_after_sales_setup_requires_successful_framework_connection(qtbot) -> None:
    settings = _Settings()
    credentials = InMemoryCredentialStore()
    calls: list[tuple[str, str, str, str]] = []
    reloads: list[bool] = []
    page = AfterSalesAiSetupPage(
        settings,  # type: ignore[arg-type]
        credentials,
        lambda: reloads.append(True),
        connection_tester=lambda *args: calls.append(args),
    )
    qtbot.addWidget(page)
    page.activate()
    page.api_key_edit.setText("secret-value")
    page.model_edit.setText("deepseek-chat")
    page.test_button.click()

    assert page.verified is True
    assert page.continue_button.isEnabled()
    assert credentials.has_secret("deepseek")
    assert calls and calls[0][0] == "deepseek"
    assert reloads == [True]
    assert page.api_key_edit.text() == ""


def test_after_sales_task_requires_batch_consent(qtbot, tmp_path) -> None:
    source = tmp_path / "case.xlsx"
    source.write_bytes(b"test")
    page = ModuleTaskPage()
    qtbot.addWidget(page)
    page.set_module(
        "after_sales",
        "售后统计",
        [".xlsx"],
        framework_ai_required=True,
    )
    page.add_files([source])
    assert not page.run_button.isEnabled()
    page.ai_consent.setChecked(True)
    assert page.run_button.isEnabled()
    assert page.run_button.text() == "开始智能分析并进入人工复核"
