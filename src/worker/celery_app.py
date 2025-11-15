# -*- coding: utf-8 -*-
"""
Celery 애플리케이션 인스턴스를 생성하고 설정합니다.

이 파일은 Celery 워커와 Celery Beat 스케줄러를 실행할 때의 진입점(entrypoint) 역할을 합니다.
- 워커 실행 예: `celery -A src.worker.celery_app:celery_app worker -l info`
- 비트 실행 예: `celery -A src.worker.celery_app:celery_app beat -l info`
"""

from celery import Celery
from celery.schedules import crontab

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
    # task_track_started=True: 태스크가 '시작됨' 상태를 보고하도록 설정합니다.
    # 이를 통해 작업의 현재 상태를 더 상세하게 추적할 수 있습니다.
    task_track_started=True,
    # --- Celery Beat 스케줄 설정 ---
    # 주기적으로 실행될 작업들을 정의합니다. (Celery Beat 프로세스가 필요)
    beat_schedule={
        # 1분마다 사용자가 예약한 작업을 확인하고 실행하는 태스크
        "run-user-tasks-every-minute": {
            "task": "src.worker.tasks.check_and_run_user_tasks",  # 실행할 태스크의 전체 경로
            "schedule": crontab(
                minute="*"
            ),  # crontab 형식으로 실행 주기 설정 (매 분)
            "options": {"expires": 60},  # 작업이 60초 안에 시작되지 않으면 만료
        },
        # 매일 오전 4시 5분에 오래된 문서를 확인하는 태스크
        "check-stale-documents-every-day": {
            "task": "src.worker.tasks.check_stale_documents",
            "schedule": crontab(
                minute="5", hour="4"
            ),  # 매일 4:05 AM (서버 시간 기준)
        },
    },
    # --- 태스크 동작 관련 설정 ---
    # task_acks_late = True: 태스크가 성공적으로 완료된 후에만 메시지 큐에서 해당 작업을 제거(ack)합니다.
    # 만약 워커가 작업 도중 예기치 않게 종료되면, 작업이 큐에 남아있어 다른 워커가 재시도할 수 있습니다.
    task_acks_late=True,
    # worker_prefetch_multiplier = 1: 각 워커가 한 번에 하나의 작업만 미리 가져오도록 설정합니다.
    # 오래 걸리는 작업이 다른 짧은 작업을 막는 것을 방지하는 데 도움이 됩니다.
    worker_prefetch_multiplier=1,
)

logger.info("Celery 애플리케이션 설정이 완료되었습니다.")
logger.info(f"포함된 태스크 모듈: {celery_app.conf.include}")
logger.info(f"설정된 스케줄: {list(celery_app.conf.beat_schedule.keys())}")
