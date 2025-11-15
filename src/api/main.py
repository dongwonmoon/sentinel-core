# -*- coding: utf-8 -*-
"""
FastAPI 애플리케이션의 메인 진입점(Entrypoint)입니다.

이 파일의 역할:
- FastAPI 앱 인스턴스 생성 및 기본 정보 설정
- CORS(Cross-Origin Resource Sharing) 미들웨어 설정
- API 엔드포인트 라우터(Router) 등록
- 요청 처리 시간 측정을 위한 커스텀 미들웨어 추가
- API 서버의 상태를 확인하기 위한 루트 엔드포인트('/') 정의
"""

import time
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# 내부 모듈 임포트
from ..core.config import get_settings
from ..core.logger import get_logger
from ..core.metrics import collector, router as metrics_router
from .endpoints import auth, chat, documents, admin, notifications, scheduler

# --- 초기 설정 ---
# 설정 객체 로드
settings = get_settings()
# 로거 인스턴스 생성
logger = get_logger(__name__)

logger.info("FastAPI 애플리케이션 초기화를 시작합니다...")

# --- FastAPI 앱 인스턴스 생성 ---
# 설정 파일(config.yml)에 정의된 앱 제목과 설명을 사용하여 FastAPI 앱을 생성합니다.
app = FastAPI(
    title=settings.app.title,
    description=settings.app.description,
    version="1.0.0",
)
logger.info(f"'{settings.app.title}' v1.0.0 앱 인스턴스가 생성되었습니다.")

# --- 미들웨어(Middleware) 설정 ---

# 1. CORS 미들웨어: 다른 도메인에서의 API 요청을 허용하기 위한 설정입니다.
# 개발 환경에서는 모든 출처('*')를 허용하여 편의성을 높입니다.
# 프로덕션 환경에서는 보안을 위해 `allow_origins` 목록에 실제 프론트엔드 서비스의 도메인만 명시해야 합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 출처에서의 요청을 허용
    allow_credentials=True,  # 요청에 쿠키를 포함하도록 허용
    allow_methods=["*"],  # 모든 HTTP 메소드(GET, POST, 등)를 허용
    allow_headers=["*"],  # 모든 HTTP 헤더를 허용
)
logger.info("CORS 미들웨어가 모든 출처에 대해 허용 모드로 추가되었습니다.")


# 2. 요청 처리 시간 측정 미들웨어
class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    각 API 요청의 처리 시간을 측정하여 Prometheus 메트릭으로 기록하는 미들웨어입니다.
    """

    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        # 다음 미들웨어 또는 실제 엔드포인트로 요청을 전달합니다.
        response = await call_next(request)
        end_time = time.perf_counter()

        duration_ms = (end_time - start_time) * 1000
        path = request.url.path

        # 메트릭 수집기에 요청 경로와 처리 시간을 기록합니다.
        collector.observe_request(path, duration_ms)
        logger.debug(f"Request '{path}' processed in {duration_ms:.2f}ms")

        return response


app.add_middleware(RequestTimingMiddleware)
logger.info(
    "요청 처리 시간 측정을 위한 'RequestTimingMiddleware'가 추가되었습니다."
)


# --- 라우터(Router) 등록 ---
# 각 기능별로 분리된 엔드포인트들을 메인 앱에 등록합니다.
# 이렇게 모듈화하면 코드 관리가 용이해집니다.
logger.info("API 라우터를 등록합니다...")
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
logger.debug("'/api/auth' 라우터가 등록되었습니다.")

app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
logger.debug("'/api/chat' 라우터가 등록되었습니다.")

app.include_router(
    documents.router, prefix="/api/documents", tags=["Documents"]
)
logger.debug("'/api/documents' 라우터가 등록되었습니다.")

app.include_router(admin.router, prefix="/api/admin", tags=["Admin"])
logger.debug("'/api/admin' 라우터가 등록되었습니다.")

app.include_router(
    notifications.router, prefix="/api/notifications", tags=["Notifications"]
)
logger.debug("'/api/notifications' 라우터가 등록되었습니다.")

app.include_router(
    scheduler.router, prefix="/api/scheduler", tags=["Scheduler"]
)
logger.debug("'/api/scheduler' 라우터가 등록되었습니다.")

app.include_router(metrics_router, prefix="/metrics", tags=["Metrics"])
logger.debug("'/metrics' 라우터가 등록되었습니다.")


# --- 루트 엔드포인트 ---
@app.get("/", tags=["Root"])
async def read_root():
    """
    루트 엔드포인트.
    API 서버가 정상적으로 실행 중인지 간단히 확인할 수 있는 상태 확인용 엔드포인트입니다.
    """
    logger.debug("루트 엔드포인트 '/'가 호출되었습니다.")
    return {"message": f"Welcome to {settings.app.title}"}


logger.info("FastAPI 애플리케이션 초기화가 완료되었습니다.")
