from dataclasses import dataclass
from typing import Literal, Protocol
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
    response_format: Literal["text", "json_object"] = "text"


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


class UnavailableProvider:
    """Keep the desktop usable while making an invalid online setup explicit."""

    def __init__(self, provider_id: str, reason: str) -> None:
        self.provider_id = provider_id
        self.reason = reason

    def complete(self, request: AIRequest) -> AIResponse:
        del request
        raise ProviderConfigurationError(self.reason)

    def __repr__(self) -> str:
        return f"UnavailableProvider(provider_id={self.provider_id!r})"


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
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
        }
        if request.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=payload,
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


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek's official OpenAI Chat Completions compatible endpoint."""

    provider_id = "deepseek"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        client: httpx.Client | None = None,
    ) -> None:
        super().__init__(base_url, api_key, client)
