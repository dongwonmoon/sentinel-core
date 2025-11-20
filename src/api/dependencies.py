# -*- coding: utf-8 -*-
"""
FastAPI 의존성 주입(Dependency Injection) 시스템을 위한 "제공자(Provider)" 함수들을 정의합니다.

이 모듈의 함수들은 FastAPI의 `Depends()`를 통해 각 API 엔드포인트에 필요한
객체(예: DB 세션, 설정 객체, 인증된 사용자 정보)를 주입하는 역할을 합니다.

주요 개념:
- **싱글톤 의존성**: `@lru_cache`를 사용하여 애플리케이션 전체에서 단 하나의 인스턴스만 생성되도록 합니다.
  (예: `get_settings`, `get_agent`)
- **요청 단위 의존성(Request-scoped)**: 모든 API 요청마다 새로 생성되고, 요청이 끝나면 정리됩니다.
  (예: `get_db_session`)
"""

from functools import lru_cache
from typing import AsyncGenerator
import time
import redis.asyncio as aioredis

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core import factories
from ..core.agent import Orchestrator
from ..core.config import Settings, get_settings
from ..core.security import verify_token
from ..components.vector_stores.pg_vector_store import PgVectorStore
from ..core.logger import get_logger
from . import schemas

logger = get_logger(__name__)


# OAuth2PasswordBearer는 FastAPI가 토큰 기반 인증을 처리하는 데 사용하는 클래스입니다.
# `tokenUrl`은 클라이언트가 사용자 이름과 비밀번호를 보내 토큰을 받아야 하는 엔드포인트 경로를 지정합니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


@lru_cache
def get_agent() -> Orchestrator:
    """
    애플리케이션의 핵심 로직을 수행하는 `Agent` 인스턴스를 생성하고 반환합니다.

    `@lru_cache`를 통해 `Agent`와 그에 필요한 모든 하위 컴포넌트(LLM, Vector Store 등)들이
    애플리케이션 시작 시 단 한 번만 초기화되도록 합니다. 이는 비용이 큰 모델 로딩 등의
    작업을 반복하지 않게 하여 성능을 크게 향상시킵니다.
    """
    logger.info("핵심 Agent 및 하위 컴포넌트(LLM, Vector Store 등)를 초기화합니다...")
    start_time = time.time()

    settings = get_settings()

    # 1. 팩토리 패턴(Factory Pattern)을 사용하여 설정(config.yml)에 따라 각 컴포넌트를 동적으로 생성합니다.
    #    이를 통해 코드 변경 없이 설정 파일 수정만으로 사용할 LLM, 벡터 저장소 등을 교체할 수 있습니다.
    logger.debug("임베딩 모델 생성 중...")
    embedding_model = factories.create_embedding_model(
        settings.embedding, settings, settings.OPENAI_API_KEY
    )

    logger.debug("벡터 저장소 생성 중...")
    vector_store = factories.create_vector_store(
        settings.vector_store, settings, embedding_model
    )

    logger.debug("LLM 생성 중...")
    llm = factories.create_llm(settings.llm, settings, settings.OPENAI_API_KEY)

    logger.debug("리랭커 생성 중...")
    reranker = factories.create_reranker(settings.reranker)

    # logger.debug("활성화된 도구들 가져오는 중...")
    # tools = factories.get_tools(settings.tools_enabled)

    # 2. 생성된 컴포넌트들을 `Agent` 클래스에 의존성으로 주입하여 최종 에이전트 인스턴스를 생성합니다.
    agent = Orchestrator(
        llm=llm,
        vector_store=vector_store,
        reranker=reranker,
        # tools=tools,
    )

    end_time = time.time()
    logger.info(f"Agent 초기화 완료. (소요 시간: {end_time - start_time:.2f}초)")
    return agent


@lru_cache
def get_redis_pool() -> aioredis.ConnectionPool:
    """
    세션 저장을 위한 Redis 커넥션 풀을 생성하고 캐시합니다.
    Celery(0, 1)와 다른 DB(2)를 사용합니다.
    커넥션 풀을 사용하면 요청마다 TCP 연결을 새로 맺고 끊는 오버헤드를 줄여 성능을 향상시킵니다.
    """
    logger.info("세션 캐시용 Redis 커넥션 풀을 생성합니다.")
    settings = get_settings()
    return aioredis.ConnectionPool.from_url(
        f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/2",
        encoding="utf-8",
        decode_responses=True,
    )


async def get_redis_client(
    pool: aioredis.ConnectionPool = Depends(get_redis_pool),
) -> AsyncGenerator[aioredis.Redis, None]:
    """
    API 요청마다 Redis 풀에서 클라이언트를 가져오는 의존성입니다.
    `async with` 구문을 사용하여 요청 처리가 끝나면 클라이언트가 자동으로 풀에 반환되도록 합니다.
    """
    logger.debug("Redis 풀에서 클라이언트를 가져옵니다.")
    async with aioredis.Redis(connection_pool=pool) as redis:
        try:
            yield redis
        except Exception as e:
            logger.error(f"Redis 클라이언트 작업 중 오류 발생: {e}", exc_info=True)
            raise
        finally:
            # `async with` 블록이 끝나면 클라이언트는 자동으로 풀에 반환되므로,
            # 여기서는 로깅만 수행합니다.
            logger.debug("Redis 클라이언트를 풀에 반환합니다.")


# --- 요청 단위 의존성 (API 요청마다 생성 및 소멸) ---


async def get_db_session(
    agent: Orchestrator = Depends(get_agent),
) -> AsyncGenerator[AsyncSession, None]:
    """
    API 요청마다 새로운 데이터베이스 세션(AsyncSession)을 생성하고,
    요청 처리가 완료되면 세션을 자동으로 닫는 제너레이터(Generator) 의존성입니다.

    `yield`를 통해 세션을 엔드포인트에 제공하고, 엔드포트의 로직이 모두 실행된 후
    `finally` 블록이 실행되어 세션 리소스를 안전하게 해제합니다.
    이를 통해 세션 유출(Session Leak)을 방지합니다.

    Args:
        agent (Agent): `get_agent`로부터 주입된 싱글톤 Agent 인스턴스.

    Yields:
        AsyncSession: 비동기 데이터베이스 작업을 위한 SQLAlchemy 세션 객체.
    """
    vector_store = agent.vector_store
    # PgVectorStore 만이 AsyncSession 팩토리를 노출하므로, 다른 벡터 스토어가 활성화된 경우
    # 잘못된 의존성 사용을 조기에 차단한다.
    if not isinstance(vector_store, PgVectorStore):
        logger.error("PgVectorStore가 아닌 벡터 저장소에 DB 세션을 요청했습니다.")
        raise HTTPException(
            status_code=501,
            detail="Database session is only available when using PgVectorStore.",
        )

    session_local = vector_store.AsyncSessionLocal
    if not session_local:
        logger.critical("데이터베이스 세션 팩토리가 초기화되지 않았습니다!")
        raise HTTPException(
            status_code=500,
            detail="Database session factory is not initialized.",
        )

    session: AsyncSession = session_local()
    logger.debug(f"DB 세션 [ID: {id(session)}] 생성됨.")
    try:
        # `yield` 키워드는 제너레이터의 실행을 일시 중지하고, 세션 객체를 FastAPI 경로 함수로 전달합니다.
        # 경로 함수의 실행이 완료될 때까지 이 함수의 실행은 여기서 멈춥니다.
        yield session
        # 경로 함수에서 명시적인 예외가 발생하지 않았다면, 모든 DB 변경사항을 커밋합니다.
        await session.commit()
        logger.debug(f"DB 세션 [ID: {id(session)}] 커밋됨.")
    except Exception as e:
        # 경로 함수 실행 중 예외가 발생하면, 현재 트랜잭션의 모든 변경사항을 롤백하여
        # 데이터베이스의 일관성을 유지합니다.
        logger.error(
            f"DB 세션 [ID: {id(session)}]에서 예외 발생. 롤백합니다. 에러: {e}",
            exc_info=True,
        )
        await session.rollback()
        # 발생한 예외를 다시 상위로 전달하여 FastAPI의 기본 예외 처리기가 처리하도록 합니다.
        raise
    finally:
        # 요청 처리의 성공/실패 여부와 관계없이, `finally` 블록은 항상 실행됩니다.
        # 여기서 세션을 닫아 데이터베이스 커넥션을 풀에 반환하고 리소스를 정리합니다.
        await session.close()
        logger.debug(f"DB 세션 [ID: {id(session)}] 닫힘.")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> schemas.UserInDB:
    """
    HTTP 요청 헤더의 JWT 토큰을 검증하고, 데이터베이스에서 최신 사용자 정보를 조회하여 반환합니다.
    인증 실패 시 `HTTPException` (401 Unauthorized)을 발생시킵니다.

    Args:
        token (str): `oauth2_scheme`에 의해 Authorization 헤더에서 추출된 Bearer 토큰.
        session (AsyncSession): `get_db_session`으로부터 주입된 DB 세션.

    Returns:
        schemas.UserInDB: 인증된 사용자의 정보 (DB 스키마 모델).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="자격 증명을 검증할 수 없습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # JWT 토큰의 유효성(서명, 만료 시간 등)을 검증합니다.
    token_data = verify_token(token, credentials_exception)
    logger.debug(f"토큰 검증 성공: 사용자 '{token_data.username}'")

    # 토큰에 포함된 사용자 이름으로 DB에서 실제 사용자 정보를 조회합니다.
    # 이는 사용자가 비활성화되거나 권한이 변경된 경우를 실시간으로 반영하기 위함입니다.
    stmt = text(
        """
        SELECT u.*, p.profile_text 
        FROM users u
        LEFT JOIN user_profile p ON u.user_id = p.user_id
        WHERE u.username = :username
    """
    )
    result = await session.execute(stmt, {"username": token_data.username})
    user_row = result.fetchone()

    if user_row is None:
        logger.warning(
            f"토큰은 유효하지만 DB에 사용자 '{token_data.username}'가 존재하지 않습니다."
        )
        raise credentials_exception

    user = schemas.UserInDB(**user_row._asdict())

    if not user.is_active:
        logger.warning(f"비활성화된 사용자 '{user.username}'의 접근 시도.")
        raise HTTPException(status_code=400, detail="비활성화된 사용자입니다.")

    logger.debug(f"사용자 '{user.username}' 인증 및 정보 조회 완료.")
    return user
