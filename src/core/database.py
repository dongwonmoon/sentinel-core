# src/core/database.py
# -*- coding: utf-8 -*-
"""
데이터베이스 연결 및 세션 관리를 담당하는 핵심 인프라 모듈입니다.
비즈니스 로직(Agent, VectorStore)과 분리되어 독립적으로 동작합니다.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

logger.info("데이터베이스 엔진 초기화를 시작합니다...")

# 1. 비동기 데이터베이스 엔진 생성
# pool_pre_ping=True: 연결 유효성을 주기적으로 확인하여 끊긴 연결로 인한 오류 방지
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)

# 2. 비동기 세션 팩토리 생성
# 이 객체를 호출하면 새로운 DB 세션(AsyncSession)이 생성됩니다.
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

logger.info("글로벌 데이터베이스 엔진 및 세션 팩토리가 준비되었습니다.")
