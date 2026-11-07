from anthropic import AsyncAnthropic
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from lacaze.infrastructure.settings import Settings


def create_model(settings: Settings) -> tuple[AnthropicModel, AsyncAnthropic]:
    if not settings.auth_token and not settings.api_key:
        raise ValueError(
            "Set ANTHROPIC_AUTH_TOKEN or ANTHROPIC_API_KEY in your shell or local .env"
        )
    client = AsyncAnthropic(
        base_url=settings.base_url.rstrip("/") + "/",
        auth_token=settings.auth_token.get_secret_value() if settings.auth_token else None,
        api_key=settings.api_key.get_secret_value() if settings.api_key else None,
        timeout=settings.request_timeout_seconds,
        max_retries=0,
    )
    return AnthropicModel(
        settings.model_name, provider=AnthropicProvider(anthropic_client=client)
    ), client
