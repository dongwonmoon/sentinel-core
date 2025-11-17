"""
애플리케이션의 주요 동작을 관측하고 모니터링하기 위한 경량 메트릭 수집 시스템입니다.

이 모듈은 Prometheus와 같은 외부 모니터링 시스템에 대한 의존성 없이,
메모리 내에서 간단한 메트릭(요청 횟수, 처리 시간, 카운터 등)을 수집하는
기능을 제공합니다.

주요 기능:
- API 엔드포인트별 요청 횟수 및 평균 처리 시간 추적.
- 에이전트의 도구 사용 횟수 등 임의의 이벤트 카운팅.
- 수집된 메트릭을 JSON 형식으로 제공하는 `/metrics` 엔드포인트.

이 시스템은 간단한 성능 모니터링 및 디버깅에 유용합니다.
더 복잡하고 영구적인 모니터링이 필요한 프로덕션 환경에서는
Prometheus, Datadog 등 전문적인 모니터링 도구와 연동하는 것을 고려해야 합니다.
"""

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict

from fastapi import APIRouter

router = APIRouter()


@dataclass
class RequestStats:
    """
    특정 API 경로(path)에 대한 요청 통계를 추적하는 데이터 클래스입니다.
    요청 횟수(`count`)와 총 처리 시간(`total_duration`)을 저장합니다.
    """

    count: int = 0
    total_duration: float = 0.0

    def observe(self, duration: float):
        """새로운 요청 처리 시간을 기록하고 카운트를 1 증가시킵니다."""
        self.count += 1
        self.total_duration += duration

    def snapshot(self) -> Dict[str, float]:
        """현재까지의 통계를 바탕으로 평균 처리 시간을 계산하여 스냅샷을 반환합니다."""
        avg_ms = (
            (self.total_duration / self.count) * 1000 if self.count else 0.0
        )
        return {"count": self.count, "avg_duration_ms": avg_ms}


class MetricsCollector:
    """
    애플리케이션 전역에서 수집된 메트릭을 보관하는 스레드 안전(thread-safe) 수집기입니다.

    이 클래스는 싱글턴(singleton)처럼 사용되며, `collector`라는 단일 인스턴스를 통해
    애플리케이션의 여러 부분(예: API 미들웨어, 에이전트 노드)에서 메트릭을 기록할 수 있습니다.
    내부적으로 `threading.Lock`을 사용하여 여러 스레드에서 동시에 접근해도 데이터의 일관성을 보장합니다.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._requests: Dict[str, RequestStats] = defaultdict(RequestStats)
        self._counters: Dict[str, int] = defaultdict(int)

    def observe_request(self, path: str, duration: float):
        """API 요청 처리 시간 메트릭을 기록합니다."""
        with self._lock:
            self._requests[path].observe(duration)

    def increment_counter(self, name: str, value: int = 1):
        """
        지정된 이름의 카운터를 1만큼(또는 주어진 `value`만큼) 증가시킵니다.
        (예: `collector.increment_counter("rag_tool_usage")`)
        """
        with self._lock:
            self._counters[name] += value

    def snapshot(self):
        """
        현재까지 수집된 모든 메트릭의 스냅샷을 생성하여 반환합니다.
        이 메서드는 `/metrics` 엔드포인트에서 호출됩니다.
        """
        with self._lock:
            return {
                "request_metrics": {
                    path: stats.snapshot()
                    for path, stats in self._requests.items()
                },
                "counters": dict(self._counters),
                "generated_at": time.time(),
            }


# 애플리케이션 전역에서 사용될 MetricsCollector의 싱글턴 인스턴스
collector = MetricsCollector()


@router.get("/metrics")
async def get_metrics():
    """
    현재 메모리에 수집된 모든 메트릭의 스냅샷을 JSON 형식으로 반환합니다.

    이 엔드포인트를 주기적으로 호출하여 시스템의 상태를 모니터링할 수 있습니다.
    예를 들어, `avg_duration_ms`가 점차 증가한다면 특정 API의 성능 저하를 의심할 수 있습니다.
    """
    return collector.snapshot()
