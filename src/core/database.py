# src/core/database.py
# -*- coding: utf-8 -*-
"""
데이터베이스 연결 및 세션 관리를 담당하는 모듈.

SQLAlchemy를 사용하여 비동기 데이터베이스 엔진과 세션 팩토리를 설정합니다.
이 모듈에서 생성된 `AsyncSessionLocal`은 의존성 주입을 통해 API 엔드포인트에서 사용됩니다.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from .config import get_settings
from .logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

logger.info("데이터베이스 엔진 및 세션 설정을 시작합니다...")

# SQLAlchemy 비동기 엔진을 생성합니다.
# 이 엔진은 애플리케이션 수명 주기 동안 한 번만 생성되어야 합니다.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # 커넥션 풀에서 연결을 가져올 때마다 연결 유효성 검사를 수행하여, DB 연결이 끊어지는 문제 방지
    echo=False,  # True로 설정하면 실행되는 모든 SQL 쿼리를 로깅합니다 (디버깅용)
)

# 비동기 세션을 생성하는 팩토리 클래스입니다.
# FastAPI의 Depends()와 함께 사용되어 각 요청마다 독립적인 DB 세션을 제공합니다.
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # commit 후에도 ORM 객체의 상태를 유지하여, 객체에 계속 접근할 수 있도록 함
    autoflush=False,  # 세션이 자동으로 flush되지 않도록 설정. 수동으로 flush를 제어
)

logger.info("데이터베이스 엔진 및 세션 팩토리가 성공적으로 생성되었습니다.")
