"""요청/에이전트 동작을 관측하기 위한 경량 헬퍼."""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict

from fastapi import APIRouter

router = APIRouter()


@dataclass
class RequestStats:
    """경로별 요청 횟수와 평균 시간을 추적."""

    count: int = 0
    total_duration: float = 0.0

    def observe(self, duration: float):
        self.count += 1
        self.total_duration += duration

    def snapshot(self) -> Dict[str, float]:
        avg = self.total_duration / self.count if self.count else 0.0
        return {"count": self.count, "avg_duration_ms": avg * 1000}


class MetricsCollector:
    """앱 전역에서 수집된 지표를 보관하는 단순 수집기."""

    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Dict[str, RequestStats] = defaultdict(RequestStats)
        self._counters: Dict[str, int] = defaultdict(int)

    def observe_request(self, path: str, duration: float):
        with self._lock:
            self._requests[path].observe(duration)

    def increment_counter(self, name: str, value: int = 1):
        with self._lock:
            self._counters[name] += value

    def snapshot(self):
        with self._lock:
            return {
                "request_metrics": {
                    path: stats.snapshot()
                    for path, stats in self._requests.items()
                },
                "counters": dict(self._counters),
                "generated_at": time.time(),
            }


collector = MetricsCollector()


@router.get("/metrics")
async def get_metrics():
    """현재 메모리에 쌓인 지표 스냅샷을 JSON으로 반환."""
    return collector.snapshot()
