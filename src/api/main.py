# -*- coding: utf-8 -*-
"""
FastAPI 애플리케이션의 메인 진입점(Entrypoint)입니다.

이 파일의 역할:
- FastAPI 앱 인스턴스 생성: 애플리케이션의 기본 정보를 설정합니다.
- 미들웨어(Middleware) 설정: 모든 API 요청에 공통적으로 적용될 로직(CORS, 로깅, 메트릭 수집 등)을 추가합니다.
- API 라우터(Router) 등록: 각 기능별로 분리된 엔드포인트들을 모듈화하여 메인 앱에 연결합니다.
- 상태 확인 엔드포인트 정의: API 서버가 정상적으로 실행 중인지 확인할 수 있는 경로를 제공합니다.
"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

# 내부 모듈 임포트
from ..core.config import get_settings
from ..core.logger import get_logger
from .endpoints import auth, chat

# --- 초기 설정 ---
# 애플리케이션 설정 객체를 로드합니다.
settings = get_settings()
# 전역 로거 인스턴스를 생성합니다.
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
# 미들웨어는 모든 요청/응답에 대해 특정 처리를 수행하는 강력한 도구입니다.

# 1. CORS 미들웨어: 다른 도메인(Origin)에서의 API 요청을 허용하기 위한 설정입니다.
#    웹 프론트엔드와 백엔드 API가 다른 도메인에서 호스팅될 때 필수적입니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*"
    ],  # 중요: 프로덕션 환경에서는 보안을 위해 실제 프론트엔드 도메인 목록으로 교체해야 합니다.
    allow_credentials=True,  # 요청에 쿠키를 포함하도록 허용합니다. (인증에 필요)
    allow_methods=["*"],  # 모든 HTTP 메소드(GET, POST, 등)를 허용합니다.
    allow_headers=["*"],  # 모든 HTTP 헤더를 허용합니다.
)
logger.warning(
    "CORS 미들웨어가 모든 출처('*')를 허용하도록 설정되었습니다. 프로덕션 배포 전 반드시 수정해야 합니다."
)


# --- 라우터(Router) 등록 ---
# 각 기능별로 분리된 엔드포인트(라우터)들을 메인 앱에 등록합니다.
# `prefix`는 해당 라우터의 모든 엔드포인트에 공통적으로 적용될 URL 경로 접두사입니다.
# `tags`는 OpenAPI 문서(예: /docs)에서 엔드포인트를 그룹화하는 데 사용됩니다.
logger.info("API 라우터를 등록합니다...")
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
logger.info("모든 API 라우터가 성공적으로 등록되었습니다.")


# --- 루트 엔드포인트 ---
@app.get("/", tags=["Root"])
async def read_root():
    """
    루트 엔드포인트 ('/').
    API 서버가 정상적으로 실행 중인지 간단히 확인할 수 있는 상태 확인(Health Check)용 엔드포인트입니다.
    운영 환경에서 로드 밸런서나 쿠버네티스의 Liveness/Readiness Probe 등으로 활용될 수 있습니다.
    """
    logger.debug("루트 엔드포인트 '/'가 호출되었습니다.")
    return {"message": f"Welcome to {settings.app.title}"}


logger.info("FastAPI 애플리케이션 초기화가 완료되었습니다.")
