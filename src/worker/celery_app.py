# -*- coding: utf-8 -*-
"""
Celery 애플리케이션 인스턴스를 생성하고 설정합니다.

이 파일은 Celery 워커와 Celery Beat 스케줄러를 실행할 때의 진입점(entrypoint) 역할을 합니다.
- 워커 실행 예: `celery -A src.worker.celery_app:celery_app worker -l info`
- 비트 실행 예: `celery -A src.worker.celery_app:celery_app beat -l info`
"""

from celery import Celery

from ..core.config import get_settings
from ..core.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

logger.info("Celery 애플리케이션 설정을 시작합니다...")
logger.info(f"Celery 브로커: {settings.CELERY_BROKER_URL}")
logger.info(f"Celery 백엔드: {settings.CELERY_RESULT_BACKEND}")

# --- Celery 앱 인스턴스 생성 ---
# `main` 인자는 태스크 이름의 기본 접두사로 사용됩니다.
celery_app = Celery(
    "sentinel_tasks",
    broker=settings.CELERY_BROKER_URL,  # 작업을 받아올 메시지 큐 (Redis) 주소
    backend=settings.CELERY_RESULT_BACKEND,  # 작업 결과를 저장할 곳 (Redis) 주소
    include=[
        "src.worker.tasks"
    ],  # 워커가 시작될 때 자동으로 임포트할 태스크 모듈 목록
)

# --- Celery 상세 설정 ---
celery_app.conf.update(
    # task_track_started=True: 태스크가 '시작됨(STARTED)' 상태를 백엔드에 보고하도록 설정합니다.
    # 기본적으로는 '대기(PENDING)'와 '성공(SUCCESS)'/'실패(FAILURE)' 상태만 보고됩니다.
    # 이 설정을 통해 작업의 현재 진행 상태를 더 상세하게 추적할 수 있습니다.
    task_track_started=True,
    # --- 태스크 신뢰성 및 분배 관련 설정 ---
    # task_acks_late = True: 태스크가 성공적으로 완료된 후에만 브로커에게 작업 수신 확인(ack)을 보냅니다.
    # 만약 워커가 작업 처리 도중 예기치 않게 종료되면, 해당 작업은 큐에 그대로 남아있어
    # 다른 워커가 가져가서 재시도할 수 있습니다. (at-least-once delivery 보장)
    task_acks_late=True,
    # worker_prefetch_multiplier = 1: 각 워커 프로세스가 한 번에 하나의 작업만 미리 가져오도록(prefetch) 설정합니다.
    # 기본값은 4이며, 이 경우 오래 걸리는 작업(예: 대용량 파일 인덱싱)이 하나라도 있으면
    # 나머지 3개의 미리 가져온 짧은 작업들이 해당 워커에서 실행되지 못하고 대기하게 됩니다.
    # 1로 설정하면 워커가 현재 작업을 마쳐야만 다음 작업을 가져오므로, 작업 분배 효율이 향상됩니다.
    worker_prefetch_multiplier=1,
)

logger.info("Celery 애플리케이션 설정이 완료되었습니다.")
logger.info(f"포함된 태스크 모듈: {celery_app.conf.include}")
logger.info(f"설정된 스케줄: {list(celery_app.conf.beat_schedule.keys())}")
