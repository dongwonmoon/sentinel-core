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
        """
        특정 네임스페이스와 사용자에 대한 요청이 속도 제한 내에 있는지 확인합니다.
        제한을 초과하면 ValueError를 발생시킵니다.

        이 메서드는 '슬라이딩 윈도우(Sliding Window)' 알고리즘을 사용합니다.
        - 각 사용자의 요청 타임스탬프를 덱(deque)에 저장합니다.
        - 새로운 요청이 들어올 때마다, 현재 시간(now)을 기준으로 윈도우 크기(window_seconds)를
          벗어난 오래된 타임스탬프들을 덱의 왼쪽에서부터 제거합니다.
        - 덱에 남아있는 타임스탬프의 수가 최대 요청 수(max_requests)보다 많으면 제한을 초과한 것으로 간주합니다.
        """
        now = time.monotonic()  # 시스템 재부팅 등과 무관한 단조 증가 시간 사용
        cfg = self.config.get(namespace)
        if not cfg:
            # 설정되지 않은 네임스페이스는 제한을 적용하지 않음
            return

        key = f"{namespace}:{user_key}"
        timestamps = self.history[key]

        # 윈도우를 슬라이딩: 현재 윈도우의 시작점보다 오래된 타임스탬프들을 제거합니다.
        while timestamps and now - timestamps[0] > cfg.window_seconds:
            timestamps.popleft()

        # 현재 윈도우 내의 요청 수가 최대 허용치를 초과했는지 확인합니다.
        if len(timestamps) >= cfg.max_requests:
            logger.warning(
                "Rate limit exceeded: namespace=%s user=%s", namespace, user_key
            )
            raise ValueError("Rate limit exceeded. Please try again later.")

        # 현재 요청의 타임스탬프를 기록에 추가합니다.
        timestamps.append(now)


# 애플리케이션 전체에서 사용될 속도 제한기 인스턴스입니다.
# 새로운 네임스페이스에 대한 속도 제한을 추가하려면 이 딕셔너리에 항목을 추가하면 됩니다.
# 예: "new_feature": RateLimitConfig(max_requests=20, window_seconds=300)
rate_limiter = InMemoryRateLimiter(
    {
        "chat": RateLimitConfig(max_requests=10, window_seconds=60),
        "documents": RateLimitConfig(max_requests=5, window_seconds=60),
    }
)
