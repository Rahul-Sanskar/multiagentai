"""
Retry / fallback utilities built on tenacity.

Provides
--------
with_retry(fn, ...)         — async retry with exponential back-off
RetryConfig                 — dataclass for retry parameters
fallback(primary, backup)   — try primary, fall back to backup on any exception

Usage
-----
    from utils.retry import with_retry, RetryConfig

    result = await with_retry(
        my_async_fn,
        args=(arg1,),
        kwargs={"key": "val"},
        config=RetryConfig(max_attempts=3, base_delay=0.5),
    )

    # Or as a decorator:
    @retry_async(RetryConfig(max_attempts=2))
    async def flaky_call():
        ...
"""
from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from utils.logger import get_logger

logger = get_logger("retry")

T = TypeVar("T")

# Exceptions that should NOT be retried (programmer errors / bad input)
_NO_RETRY = (ValueError, TypeError, KeyError, AttributeError)


@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 0.5       # seconds
    max_delay: float = 10.0       # seconds
    multiplier: float = 2.0
    reraise: bool = True          # re-raise last exception after exhausting retries
    retry_on: tuple[type[Exception], ...] = field(
        default_factory=lambda: (Exception,)
    )


async def with_retry(
    fn: Callable[..., Any],
    *,
    args: tuple = (),
    kwargs: dict[str, Any] | None = None,
    config: RetryConfig | None = None,
    fallback_value: Any = None,
    use_fallback: bool = False,
) -> Any:
    """
    Call an async function with retry logic.

    Parameters
    ----------
    fn             : async callable to invoke
    args / kwargs  : positional and keyword arguments for fn
    config         : RetryConfig (uses defaults if None)
    fallback_value : value to return if all retries fail and use_fallback=True
    use_fallback   : if True, return fallback_value instead of raising on exhaustion
    """
    cfg = config or RetryConfig()
    kwargs = kwargs or {}

    # Never retry on programmer errors — always excluded regardless of retry_on config
    def _should_retry(exc: BaseException) -> bool:
        if isinstance(exc, _NO_RETRY):
            return False
        return isinstance(exc, cfg.retry_on)

    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(cfg.max_attempts),
            wait=wait_exponential(
                multiplier=cfg.multiplier,
                min=cfg.base_delay,
                max=cfg.max_delay,
            ),
            retry=retry_if_exception(_should_retry),
            reraise=cfg.reraise and not use_fallback,
        ):
            with attempt:
                attempt_num = attempt.retry_state.attempt_number
                if attempt_num > 1:
                    logger.warning(
                        "retry_attempt",
                        fn=fn.__name__,
                        attempt=attempt_num,
                        max=cfg.max_attempts,
                    )
                return await fn(*args, **kwargs)

    except RetryError as exc:
        logger.error(
            "retry_exhausted",
            fn=fn.__name__,
            attempts=cfg.max_attempts,
            last_error=str(exc.last_attempt.exception()),
        )
        if use_fallback:
            return fallback_value
        raise

    except Exception as exc:
        logger.error("retry_failed", fn=fn.__name__, error=str(exc))
        if use_fallback:
            return fallback_value
        raise


def retry_async(config: RetryConfig | None = None):
    """
    Decorator version of with_retry.

    Usage
    -----
    @retry_async(RetryConfig(max_attempts=3))
    async def call_external_api():
        ...
    """
    cfg = config or RetryConfig()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await with_retry(fn, args=args, kwargs=kwargs, config=cfg)
        return wrapper
    return decorator


async def fallback(
    primary: Callable[[], Any],
    backup: Callable[[], Any],
    *,
    log_fallback: bool = True,
) -> Any:
    """
    Try primary(); if it raises any exception, call backup() instead.

    Usage
    -----
    result = await fallback(
        primary=lambda: call_llm_api(),
        backup=lambda: use_template_fallback(),
    )
    """
    try:
        return await primary()
    except Exception as exc:
        if log_fallback:
            logger.warning(
                "fallback_triggered",
                primary=getattr(primary, "__name__", "primary"),
                error=str(exc),
            )
        return await backup()
