from __future__ import annotations

import sys
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MODULE_ROOT / "src"))

from moisture.application.service_request_builder import build_knowledge_request


def _build(scopes: tuple[str, ...], needed: bool = True):
    return build_knowledge_request(
        root_job_id="draft-root",
        allowed_scopes=scopes,
        needed=needed,
        rule_hash="a" * 64,
        candidate_digest="b" * 64,
    )


def test_prefers_moisture_then_shared_and_is_stable() -> None:
    first = _build(("shared", "moisture"))
    second = _build(("MOISTURE", "shared"))

    assert first is not None and second is not None
    assert first["scope"] == "moisture"
    assert first["request_id"] == second["request_id"]
    assert first["payload"] == {"query": "竹丝水分规则适用范围复核指导"}
    assert first["requires_user_consent"] is False


def test_unauthorized_or_unneeded_request_is_omitted() -> None:
    assert _build(("customer-private",)) is None
    assert _build(("moisture",), needed=False) is None
