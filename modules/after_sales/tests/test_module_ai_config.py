from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from after_sales_agent.module_ai_config import (  # noqa: E402
    load_saved_module_ai_config,
    normalize_module_ai_config,
)


def test_saved_ai_config_is_used_only_after_explicit_module_start(monkeypatch) -> None:
    raw = json.dumps(
        {
            "provider": "deepseek",
            "api_key": "sk-test",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
        }
    )
    fake_keyring = SimpleNamespace(get_password=lambda *_args: raw)
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    monkeypatch.delenv("AFTER_SALES_USE_SAVED_AI", raising=False)

    assert load_saved_module_ai_config() is None

    monkeypatch.setenv("AFTER_SALES_USE_SAVED_AI", "1")
    loaded = load_saved_module_ai_config()
    assert loaded is not None
    assert loaded["provider"] == "deepseek"
    assert loaded["model"] == "deepseek-v4-flash"
    assert loaded["api_key"] == "sk-test"


def test_module_ai_config_rejects_plain_http_and_unknown_provider() -> None:
    assert (
        normalize_module_ai_config(
            {
                "provider": "deepseek",
                "api_key": "sk-test",
                "base_url": "http://api.deepseek.com",
                "model": "deepseek-v4-flash",
            }
        )
        is None
    )
    assert (
        normalize_module_ai_config(
            {
                "provider": "unsupported",
                "api_key": "sk-test",
                "base_url": "https://example.invalid/v1",
                "model": "example",
            }
        )
        is None
    )
