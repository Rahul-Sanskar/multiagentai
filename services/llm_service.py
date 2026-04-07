"""
LLM Service
-----------
Priority chain — first available backend wins:

  1. Groq   (GROQ_API_KEY set)      → llama3-70b-8192 via api.groq.com
  2. Ollama (local server running)  → llama3 via localhost:11434
  3. Template fallback              → agents handle this themselves

Public interface (unchanged):
  is_available()        — True if Groq or Ollama is reachable
  chat_completion(...)  — call the active backend, raises LLMError on failure
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from config import get_settings
from utils.logger import get_logger

logger = get_logger("LLMService")

# ── Backend endpoints ─────────────────────────────────────────────────────────

_GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama3-70b-8192"

_OLLAMA_URL   = "http://localhost:11434/api/chat"
_OLLAMA_MODEL = "llama3"

_TIMEOUT = 60.0   # seconds — Ollama on CPU can be slow


class LLMError(Exception):
    """Raised when all LLM backends fail."""


# ── Availability ──────────────────────────────────────────────────────────────

def is_available() -> bool:
    """
    Return True if at least one LLM backend is configured.
    Groq: checked by key presence (fast).
    Ollama: always considered potentially available (checked at call time).
    """
    settings = get_settings()
    return bool(settings.groq_api_key) or True   # Ollama always attempted as fallback


# ── Main entry point ──────────────────────────────────────────────────────────

async def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str:
    """
    Call the best available LLM backend.

    Priority: Groq → Ollama → LLMError

    Parameters
    ----------
    messages    : OpenAI-format message list
    model       : override model name (uses backend default if None)
    temperature : sampling temperature
    max_tokens  : optional token cap

    Raises
    ------
    LLMError  if all backends fail or are unavailable.
    """
    settings = get_settings()

    # ── 1. Try Groq ───────────────────────────────────────────────────────
    if settings.groq_api_key:
        try:
            result = await _groq_completion(
                messages=messages,
                model=model or _GROQ_MODEL,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=settings.groq_api_key,
            )
            logger.info("llm_response_ok", llm_source="groq",
                        model=model or _GROQ_MODEL, chars=len(result))
            return result
        except LLMError as exc:
            logger.warning("llm_groq_failed_trying_ollama", error=str(exc))

    # ── 2. Try Ollama ─────────────────────────────────────────────────────
    try:
        result = await _ollama_completion(
            messages=messages,
            model=model or _OLLAMA_MODEL,
            temperature=temperature,
        )
        logger.info("llm_response_ok", llm_source="ollama",
                    model=model or _OLLAMA_MODEL, chars=len(result))
        return result
    except LLMError as exc:
        logger.warning("llm_ollama_failed", error=str(exc))

    raise LLMError(
        "All LLM backends failed. "
        "Set GROQ_API_KEY or start Ollama (ollama serve)."
    )


# ── Groq backend ──────────────────────────────────────────────────────────────

async def _groq_completion(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int | None,
    api_key: str,
) -> str:
    """
    Call the Groq chat completions endpoint (OpenAI-compatible).
    Raises LLMError on any failure.
    """
    payload: dict[str, Any] = {
        "model":       model,
        "messages":    messages,
        "temperature": temperature,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens

    logger.info("llm_request", llm_source="groq", model=model,
                messages=len(messages))

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _GROQ_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise LLMError(f"Groq request timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise LLMError(f"Groq network error: {exc}") from exc

    if resp.status_code == 401:
        raise LLMError("Invalid Groq API key.")
    if resp.status_code == 429:
        raise LLMError("Groq rate limit exceeded.")
    if not resp.is_success:
        raise LLMError(f"Groq API error {resp.status_code}: {resp.text[:200]}")

    content = resp.json()["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise LLMError("Groq returned an empty response.")
    return content.strip()


# ── Ollama backend ────────────────────────────────────────────────────────────

async def _ollama_completion(
    messages: list[dict],
    model: str,
    temperature: float,
) -> str:
    """
    Call a local Ollama server using its /api/chat endpoint.
    Raises LLMError if Ollama is not running or the call fails.
    """
    logger.info("llm_request", llm_source="ollama", model=model,
                messages=len(messages))

    payload = {
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": temperature},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(_OLLAMA_URL, json=payload)
    except httpx.ConnectError as exc:
        raise LLMError(
            f"Ollama not reachable at {_OLLAMA_URL}. "
            "Run: ollama serve"
        ) from exc
    except httpx.TimeoutException as exc:
        raise LLMError(f"Ollama request timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise LLMError(f"Ollama network error: {exc}") from exc

    if not resp.is_success:
        raise LLMError(f"Ollama error {resp.status_code}: {resp.text[:200]}")

    content = resp.json().get("message", {}).get("content", "")
    if not content or not content.strip():
        raise LLMError("Ollama returned an empty response.")
    return content.strip()
