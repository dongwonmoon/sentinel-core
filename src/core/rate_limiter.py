"""간단한 인메모리 요청 속도 제한기."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict

from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """허용 횟수 및 시간 창을 정의하는 설정."""

    max_requests: int
    window_seconds: float


class InMemoryRateLimiter:
    """네임스페이스/사용자 기준 슬라이딩 윈도우 속도 제한기."""

    def __init__(self, config: Dict[str, RateLimitConfig]):
        self.config = config
        self.history: Dict[str, Deque[float]] = defaultdict(deque)

    async def assert_within_limit(self, namespace: str, user_key: str):
        now = time.monotonic()
        cfg = self.config.get(namespace)
        if not cfg:
            return

        key = f"{namespace}:{user_key}"
        timestamps = self.history[key]

        # 오래된 타임스탬프 정리
        while timestamps and now - timestamps[0] > cfg.window_seconds:
            timestamps.popleft()

        if len(timestamps) >= cfg.max_requests:
            logger.warning(
                "Rate limit exceeded: namespace=%s user=%s", namespace, user_key
            )
            raise ValueError("Rate limit exceeded. Please try again later.")

        timestamps.append(now)


rate_limiter = InMemoryRateLimiter(
    {
        "chat": RateLimitConfig(max_requests=10, window_seconds=60),
        "documents": RateLimitConfig(max_requests=5, window_seconds=60),
    }
)
