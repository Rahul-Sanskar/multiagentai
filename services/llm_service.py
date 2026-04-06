"""
LLM Service
-----------
Thin async wrapper around the OpenAI chat completions API.

is_available()        — returns True if OPENAI_API_KEY is configured
chat_completion(...)  — call the model, raises LLMError on failure
"""
from __future__ import annotations

from openai import AsyncOpenAI, APIError, APIConnectionError, RateLimitError, AuthenticationError
from config import get_settings
from utils.logger import get_logger

logger = get_logger("LLMService")
settings = get_settings()

_client: AsyncOpenAI | None = None


class LLMError(Exception):
    """Raised when the LLM call fails for any reason."""


def is_available() -> bool:
    """Return True if an API key is configured."""
    return bool(settings.openai_api_key)


def get_llm_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """
    Call the OpenAI chat completions endpoint.

    Raises
    ------
    LLMError  on authentication failure, rate limit, connection error, or empty response.
    """
    if not is_available():
        raise LLMError("OPENAI_API_KEY is not configured.")

    client = get_llm_client()
    model  = model or settings.default_model

    kwargs: dict = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    logger.info("llm_request", model=model, messages=len(messages))

    try:
        response = await client.chat.completions.create(**kwargs)
    except AuthenticationError as exc:
        raise LLMError(f"Invalid OpenAI API key: {exc}") from exc
    except RateLimitError as exc:
        raise LLMError(f"OpenAI rate limit exceeded: {exc}") from exc
    except APIConnectionError as exc:
        raise LLMError(f"OpenAI connection error: {exc}") from exc
    except APIError as exc:
        raise LLMError(f"OpenAI API error: {exc}") from exc

    content = response.choices[0].message.content
    if not content or not content.strip():
        raise LLMError("LLM returned an empty response.")

    logger.info("llm_response_ok", model=model, chars=len(content))
    return content.strip()
