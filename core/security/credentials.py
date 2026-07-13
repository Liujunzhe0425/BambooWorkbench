import re
from contextlib import suppress
from typing import Protocol

import keyring

SERVICE_NAME = "BambooWorkbench"
_PROVIDER_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def _validate_provider_id(provider_id: str) -> None:
    if not _PROVIDER_ID.fullmatch(provider_id):
        raise ValueError("invalid credential provider ID")


class CredentialStore(Protocol):
    def set_secret(self, provider_id: str, value: str) -> None: ...

    def get_secret(self, provider_id: str) -> str | None: ...

    def has_secret(self, provider_id: str) -> bool: ...

    def delete_secret(self, provider_id: str) -> None: ...


class InMemoryCredentialStore:
    """Test and demo backend that never serializes its values."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def set_secret(self, provider_id: str, value: str) -> None:
        _validate_provider_id(provider_id)
        if not value:
            raise ValueError("credential value must not be empty")
        self._values[provider_id] = value

    def get_secret(self, provider_id: str) -> str | None:
        _validate_provider_id(provider_id)
        return self._values.get(provider_id)

    def has_secret(self, provider_id: str) -> bool:
        return self.get_secret(provider_id) is not None

    def delete_secret(self, provider_id: str) -> None:
        _validate_provider_id(provider_id)
        self._values.pop(provider_id, None)

    def __repr__(self) -> str:
        return "InMemoryCredentialStore(<redacted>)"


class KeyringCredentialStore:
    """OS credential-vault adapter. Secrets never enter SQLite or settings files."""

    def set_secret(self, provider_id: str, value: str) -> None:
        _validate_provider_id(provider_id)
        if not value:
            raise ValueError("credential value must not be empty")
        keyring.set_password(SERVICE_NAME, provider_id, value)

    def get_secret(self, provider_id: str) -> str | None:
        _validate_provider_id(provider_id)
        return keyring.get_password(SERVICE_NAME, provider_id)

    def has_secret(self, provider_id: str) -> bool:
        return self.get_secret(provider_id) is not None

    def delete_secret(self, provider_id: str) -> None:
        _validate_provider_id(provider_id)
        with suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(SERVICE_NAME, provider_id)

    def __repr__(self) -> str:
        return "KeyringCredentialStore(service='BambooWorkbench', secret=<redacted>)"
