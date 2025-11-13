"""
FastAPI 애플리케이션의 메인 진입점(Entrypoint)입니다.
- FastAPI 앱 인스턴스 생성
- 각 엔드포인트 라우터(endpoints) 등록
- CORS 등 미들웨어 설정
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..core.config import settings
from .endpoints import auth, chat, documents

# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title=settings.app.title,
    description=settings.app.description,
    version="1.0.0",
)

# --- CORS 미들웨어 설정 ---
# 개발 환경을 위해 모든 출처, 메소드, 헤더를 허용합니다.
# 프로덕션 환경에서는 origins 목록을 실제 프론트엔드 주소로 제한해야 합니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 출처 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메소드 허용
    allow_headers=["*"],  # 모든 HTTP 헤더 허용
)

# --- 라우터 등록 ---
# 각 엔드포인트 모듈에서 정의한 router를 앱에 포함시킵니다.
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)


@app.get("/", tags=["Root"])
async def read_root():
    """루트 엔드포인트. API 서버가 정상적으로 동작하는지 확인합니다."""
    return {"message": f"Welcome to {settings.app.title}"}
