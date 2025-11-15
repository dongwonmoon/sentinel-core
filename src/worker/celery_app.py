"""
Celery 애플리케이션 인스턴스를 생성하고 설정합니다.
Celery 워커를 실행할 때 이 파일을 진입점으로 사용합니다.
(예: celery -A src.worker.celery_app:celery_app worker -l info)
"""

from celery import Celery
from celery.schedules import crontab

from ..core.config import get_settings

settings = get_settings()

# Celery 앱 인스턴스 생성
# main='sentinel_tasks'는 태스크 이름의 기본 접두사가 됩니다.
celery_app = Celery(
    "sentinel_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["src.worker.tasks"],  # 워커가 실행할 태스크 모듈을 지정합니다.
)

# Celery 설정을 업데이트 (선택 사항)
celery_app.conf.update(
    task_track_started=True,
    beat_schedule={
        "run-user-tasks-every-minute": {
            "task": "src.worker.tasks.check_and_run_user_tasks",
            "schedule": crontab(minute="*"),  # 1분마다
        },
        # 매일 오전 4시 5분에 오래된 문서가 있는지 확인
        "check-stale-documents-every-day": {
            "task": "src.worker.tasks.check_stale_documents",
            "schedule": crontab(minute="5", hour="4"),  # 매일 4:05 AM
        },
    },
)
