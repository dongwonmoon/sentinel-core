"""
FastAPI 애플리케이션의 메인 진입점(Entrypoint)입니다.
- FastAPI 앱 인스턴스 생성
- 각 엔드포인트 라우터(endpoints) 등록
- (필요 시) CORS 등 미들웨어 설정
"""
from fastapi import FastAPI
from ..core.config import settings
from .endpoints import auth, chat, documents

# FastAPI 앱 인스턴스 생성
app = FastAPI(
    title=settings.app.title,
    description=settings.app.description,
    version="1.0.0", # 버전 업데이트
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

# (필요 시) 여기에 CORS 미들웨어 등을 추가할 수 있습니다.
# from fastapi.middleware.cors import CORSMiddleware
# app.add_middleware(...)