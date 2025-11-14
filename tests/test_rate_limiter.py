import anyio

import pytest

from src.core.rate_limiter import InMemoryRateLimiter, RateLimitConfig


@pytest.mark.anyio
async def test_rate_limiter_allows_within_window():
    limiter = InMemoryRateLimiter({"chat": RateLimitConfig(max_requests=2, window_seconds=1)})
    await limiter.assert_within_limit("chat", "user")
    await limiter.assert_within_limit("chat", "user")


@pytest.mark.anyio
async def test_rate_limiter_blocks_after_threshold():
    limiter = InMemoryRateLimiter({"chat": RateLimitConfig(max_requests=1, window_seconds=5)})
    await limiter.assert_within_limit("chat", "user")
    with pytest.raises(ValueError):
        await limiter.assert_within_limit("chat", "user")


@pytest.mark.anyio
async def test_rate_limiter_sliding_window():
    limiter = InMemoryRateLimiter({"chat": RateLimitConfig(max_requests=1, window_seconds=0.05)})
    await limiter.assert_within_limit("chat", "user")
    await anyio.sleep(0.06)
    await limiter.assert_within_limit("chat", "user")
