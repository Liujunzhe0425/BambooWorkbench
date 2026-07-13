from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx


class ProviderConfigurationError(ValueError):
    pass


class ProviderResponseError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIRequest:
    model: str
    system: str
    prompt: str


@dataclass(frozen=True)
class AIResponse:
    text: str


class AIProvider(Protocol):
    def complete(self, request: AIRequest) -> AIResponse: ...


class MockProvider:
    provider_id = "mock"

    def complete(self, request: AIRequest) -> AIResponse:
        return AIResponse(f"[模拟AI分析] {request.prompt}")

    def __repr__(self) -> str:
        return "MockProvider(offline=True)"


class OpenAICompatibleProvider:
    provider_id = "openai-compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        client: httpx.Client | None = None,
    ) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ProviderConfigurationError("provider base URL must be HTTP(S)")
        if parsed.username or parsed.password:
            raise ProviderConfigurationError("provider base URL must not contain credentials")
        if not api_key:
            raise ProviderConfigurationError("provider API key is missing")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.client = client or httpx.Client(timeout=30)

    def complete(self, request: AIRequest) -> AIResponse:
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": request.model,
                "messages": [
                    {"role": "system", "content": request.system},
                    {"role": "user", "content": request.prompt},
                ],
            },
        )
        response.raise_for_status()
        try:
            text = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderResponseError("provider returned an invalid response shape") from error
        if not isinstance(text, str):
            raise ProviderResponseError("provider response content must be text")
        return AIResponse(text)

    def __repr__(self) -> str:
        return (
            f"OpenAICompatibleProvider(base_url={self.base_url!r}, "
            "api_key=<redacted>)"
        )
