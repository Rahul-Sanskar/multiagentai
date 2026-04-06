"""
Structured logging setup using structlog.

Features
--------
- JSON output in production, coloured console in debug mode
- Every log record carries: level, timestamp, logger name
- log_context() binds key/value pairs to all subsequent logs in the same
  async context (useful for request_id, pipeline_run_id, etc.)
- get_logger(name) returns a bound logger with the caller's module name
"""
from __future__ import annotations

import logging
import traceback
from contextlib import contextmanager
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

from config import get_settings

settings = get_settings()


def setup_logging() -> None:
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    shared_processors = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.debug:
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Return a structlog logger bound to the given module/component name."""
    return structlog.get_logger(name)


def bind_request_context(request_id: str, **extra: Any) -> None:
    """Bind request-scoped fields to all logs in the current async context."""
    bind_contextvars(request_id=request_id, **extra)


def clear_request_context() -> None:
    clear_contextvars()


@contextmanager
def log_context(**kwargs: Any):
    """
    Context manager that binds key/value pairs for the duration of a block.

    Usage
    -----
    with log_context(pipeline_run_id="abc123", stage="publish"):
        logger.info("doing work")   # automatically includes pipeline_run_id + stage
    """
    bind_contextvars(**kwargs)
    try:
        yield
    finally:
        # Only clear the keys we added, not the whole context
        from structlog.contextvars import get_contextvars, reset_contextvars
        ctx = get_contextvars()
        for k in kwargs:
            ctx.pop(k, None)


def format_error(exc: Exception) -> dict[str, str]:
    """Return a structured dict representation of an exception for logging."""
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
