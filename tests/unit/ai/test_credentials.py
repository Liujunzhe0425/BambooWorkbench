import pytest

from core.security.credentials import InMemoryCredentialStore


def test_memory_store_never_exposes_values_when_listed() -> None:
    store = InMemoryCredentialStore()
    store.set_secret("openai-compatible", "sk-test-secret")

    assert store.has_secret("openai-compatible") is True
    assert store.get_secret("openai-compatible") == "sk-test-secret"
    assert "sk-test-secret" not in repr(store)

    store.delete_secret("openai-compatible")
    assert store.has_secret("openai-compatible") is False


def test_memory_store_rejects_unsafe_provider_identifiers() -> None:
    store = InMemoryCredentialStore()

    with pytest.raises(ValueError, match="provider ID"):
        store.set_secret("../provider", "secret")
