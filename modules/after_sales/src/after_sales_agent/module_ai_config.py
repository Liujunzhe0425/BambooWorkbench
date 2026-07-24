from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlparse

MODULE_AI_CREDENTIAL_ID = "after-sales-ai-config"
MODULE_AI_CREDENTIAL_SERVICE = "BambooWorkbench"
USE_SAVED_AI_ENV = "AFTER_SALES_USE_SAVED_AI"
SUPPORTED_PROVIDERS = {"deepseek", "openai-compatible"}


def load_saved_module_ai_config() -> dict[str, Any] | None:
    """Load the after-sales-only AI configuration from the OS credential vault.

    The desktop host sets ``AFTER_SALES_USE_SAVED_AI=1`` only when the user
    clicks the after-sales page's intelligent-analysis button. This prevents
    self-checks, tests and unrelated module runs from silently using a saved
    paid credential.
    """

    if os.environ.get(USE_SAVED_AI_ENV) != "1":
        return None
    try:
        import keyring

        raw = keyring.get_password(MODULE_AI_CREDENTIAL_SERVICE, MODULE_AI_CREDENTIAL_ID)
    except Exception:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return normalize_module_ai_config(payload)


def normalize_module_ai_config(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    provider = str(payload.get("provider") or "deepseek").strip().casefold()
    api_key = str(payload.get("api_key") or "").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    model = str(payload.get("model") or "").strip()
    if provider not in SUPPORTED_PROVIDERS or not api_key or not model:
        return None
    parsed = urlparse(base_url)
    if parsed.scheme.casefold() != "https" or not parsed.netloc:
        return None
    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "reasoning_effort": str(payload.get("reasoning_effort") or "medium"),
        "strict": False,
    }
