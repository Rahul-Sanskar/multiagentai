"""Tests for utils/retry.py"""
import pytest
import asyncio
from utils.retry import with_retry, retry_async, fallback, RetryConfig
from utils.exceptions import AgentError


class TestWithRetry:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_attempt(self):
        calls = []

        async def fn():
            calls.append(1)
            return "ok"

        result = await with_retry(fn, config=RetryConfig(max_attempts=3))
        assert result == "ok"
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_retries_on_failure_then_succeeds(self):
        calls = []

        async def fn():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("transient error")
            return "success"

        result = await with_retry(fn, config=RetryConfig(max_attempts=3, base_delay=0.01))
        assert result == "success"
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_raises_after_exhausting_retries(self):
        async def always_fails():
            raise RuntimeError("always fails")

        with pytest.raises(RuntimeError):
            await with_retry(
                always_fails,
                config=RetryConfig(max_attempts=2, base_delay=0.01),
            )

    @pytest.mark.asyncio
    async def test_returns_fallback_value_on_exhaustion(self):
        async def always_fails():
            raise RuntimeError("fail")

        result = await with_retry(
            always_fails,
            config=RetryConfig(max_attempts=2, base_delay=0.01),
            use_fallback=True,
            fallback_value="default",
        )
        assert result == "default"

    @pytest.mark.asyncio
    async def test_does_not_retry_value_error(self):
        """ValueError should not be retried — it's a programmer error."""
        calls = []

        async def fn():
            calls.append(1)
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await with_retry(fn, config=RetryConfig(max_attempts=3, base_delay=0.01))

        # Should only be called once — no retries
        assert len(calls) == 1


class TestRetryDecorator:
    @pytest.mark.asyncio
    async def test_decorator_retries(self):
        calls = []

        @retry_async(RetryConfig(max_attempts=3, base_delay=0.01))
        async def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise RuntimeError("transient")
            return "done"

        result = await flaky()
        assert result == "done"
        assert len(calls) == 2


class TestFallback:
    @pytest.mark.asyncio
    async def test_uses_primary_when_successful(self):
        async def primary():
            return "primary_result"

        async def backup():
            return "backup_result"

        result = await fallback(primary, backup)
        assert result == "primary_result"

    @pytest.mark.asyncio
    async def test_falls_back_on_primary_failure(self):
        async def primary():
            raise RuntimeError("primary failed")

        async def backup():
            return "backup_result"

        result = await fallback(primary, backup)
        assert result == "backup_result"
