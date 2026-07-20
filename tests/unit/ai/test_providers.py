import httpx
import pytest

from core.ai.providers import (
    AIRequest,
    DeepSeekProvider,
    MockProvider,
    OpenAICompatibleProvider,
    ProviderConfigurationError,
    ProviderResponseError,
    UnavailableProvider,
)


def test_mock_provider_is_deterministic() -> None:
    request = AIRequest(model="mock-model", system="quality", prompt="分析异常")
    assert MockProvider().complete(request).text == "[模拟AI分析] 分析异常"


def test_openai_compatible_provider_uses_bearer_without_leaking_it() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        assert request.url == "https://example.invalid/v1/chat/completions"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "建议复核"}}]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider("https://example.invalid/v1", "secret", client)

    response = provider.complete(AIRequest(model="model-a", system="quality", prompt="分析"))

    assert response.text == "建议复核"
    assert "secret" not in repr(provider)


def test_provider_rejects_credentials_in_url_and_invalid_response() -> None:
    with pytest.raises(ProviderConfigurationError, match="credentials"):
        OpenAICompatibleProvider("https://user:pass@example.invalid/v1", "secret")

    client = httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"choices": []}))
    )
    provider = OpenAICompatibleProvider("https://example.invalid/v1", "secret", client)
    with pytest.raises(ProviderResponseError, match="invalid response"):
        provider.complete(AIRequest(model="model-a", system="quality", prompt="分析"))


def test_deepseek_uses_official_openai_compatible_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer deepseek-secret"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "需复核"}}]},
        )

    provider = DeepSeekProvider(
        "deepseek-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    response = provider.complete(
        AIRequest(model="deepseek-v4-flash", system="quality", prompt="分析")
    )

    assert response.text == "需复核"
    assert provider.provider_id == "deepseek"
    assert "deepseek-secret" not in repr(provider)


def test_unavailable_provider_fails_explicitly() -> None:
    provider = UnavailableProvider("deepseek", "尚未配置")
    with pytest.raises(ProviderConfigurationError, match="尚未配置"):
        provider.complete(
            AIRequest(model="deepseek-v4-flash", system="quality", prompt="分析")
        )
