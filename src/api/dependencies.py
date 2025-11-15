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

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core import factories
from ..core.agent import Agent
from ..core.config import Settings, get_settings as get_app_settings
from ..core.security import verify_token
from ..core.rate_limiter import rate_limiter
from ..components.vector_stores.pg_vector_store import PgVectorStore
from ..core.logger import get_logger
from . import schemas

logger = get_logger(__name__)

# --- 싱글톤 의존성 (애플리케이션 수명 주기 동안 한 번만 생성) ---


@lru_cache
def get_settings() -> Settings:
    """
    설정 객체를 반환합니다.
    `@lru_cache` 데코레이터를 통해 이 함수는 최초 호출 시에만 `get_app_settings()`를 실행하고,
    그 결과를 캐시합니다. 이후 모든 호출에서는 캐시된 `Settings` 객체를 즉시 반환하여,
    애플리케이션 전체에서 일관된 설정을 사용하도록 보장하고 불필요한 파일 I/O를 방지합니다.
    """
    logger.info("설정(Settings) 객체를 처음으로 로드하고 캐시합니다.")
    return get_app_settings()


# OAuth2PasswordBearer는 FastAPI가 토큰 기반 인증을 처리하는 데 사용하는 클래스입니다.
# `tokenUrl`은 클라이언트가 사용자 이름과 비밀번호를 보내 토큰을 받아야 하는 엔드포인트 경로를 지정합니다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


@lru_cache
def get_agent() -> Agent:
    """
    애플리케이션의 핵심 로직을 수행하는 `Agent` 인스턴스를 생성하고 반환합니다.

    `@lru_cache`를 통해 `Agent`와 그에 필요한 모든 하위 컴포넌트(LLM, Vector Store 등)들이
    애플리케이션 시작 시 단 한 번만 초기화되도록 합니다. 이는 비용이 큰 모델 로딩 등의
    작업을 반복하지 않게 하여 성능을 크게 향상시킵니다.
    """
    logger.info(
        "핵심 Agent 및 하위 컴포넌트(LLM, Vector Store 등)를 초기화합니다..."
    )
    start_time = time.time()

    settings = get_settings()

    # 1. 팩토리 함수를 사용하여 설정에 따라 각 컴포넌트를 생성합니다.
    logger.debug("임베딩 모델 생성 중...")
    embedding_model = factories.create_embedding_model(settings)

    logger.debug("벡터 저장소 생성 중...")
    vector_store = factories.create_vector_store(settings, embedding_model)

    logger.debug("Fast LLM 생성 중...")
    fast_llm = factories.create_llm(settings.llm.fast, settings)

    logger.debug("Powerful LLM 생성 중...")
    powerful_llm = factories.create_llm(settings.llm.powerful, settings)

    logger.debug("리랭커 생성 중...")
    reranker = factories.create_reranker(settings)

    logger.debug("활성화된 도구들 가져오는 중...")
    tools = factories.get_tools(settings.tools_enabled)

    # 2. 생성된 컴포넌트들을 `Agent` 클래스에 주입하여 인스턴스를 생성합니다.
    agent = Agent(
        fast_llm=fast_llm,
        powerful_llm=powerful_llm,
        vector_store=vector_store,
        reranker=reranker,
        tools=tools,
    )

    end_time = time.time()
    logger.info(
        f"Agent 초기화 완료. (소요 시간: {end_time - start_time:.2f}초)"
    )
    return agent


# --- 요청 단위 의존성 (API 요청마다 생성 및 소멸) ---


async def get_db_session(
    agent: Agent = Depends(get_agent),
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
    if not isinstance(vector_store, PgVectorStore):
        logger.error(
            "PgVectorStore가 아닌 벡터 저장소에 DB 세션을 요청했습니다."
        )
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
        # `yield`를 통해 생성된 세션을 API 경로 함수로 전달합니다.
        yield session
        # 경로 함수의 실행이 성공적으로 끝나면 트랜잭션을 커밋합니다.
        await session.commit()
        logger.debug(f"DB 세션 [ID: {id(session)}] 커밋됨.")
    except Exception as e:
        # 경로 함수에서 예외가 발생하면 트랜잭션을 롤백합니다.
        logger.error(
            f"DB 세션 [ID: {id(session)}]에서 예외 발생. 롤백합니다. 에러: {e}",
            exc_info=True,
        )
        await session.rollback()
        # 발생한 예외를 다시 상위로 전달하여 FastAPI가 처리하도록 합니다.
        raise
    finally:
        # 성공 여부와 관계없이 항상 세션을 닫아 리소스를 반환합니다.
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

    # 권한 그룹을 동적으로 확장합니다 (예: it_admin -> it 권한 자동 부여).
    groups = set(user_row.permission_groups)
    if "it_admin" in groups:
        groups.add("it")
    if "hr_admin" in groups:
        groups.add("hr")
    groups.add("all_users")  # 모든 사용자는 'all_users' 그룹에 속합니다.

    user = schemas.UserInDB(**user_row._asdict())
    user.permission_groups = sorted(list(groups))

    if not user.is_active:
        logger.warning(f"비활성화된 사용자 '{user.username}'의 접근 시도.")
        raise HTTPException(status_code=400, detail="비활성화된 사용자입니다.")

    logger.debug(
        f"사용자 '{user.username}' 인증 및 정보 조회 완료. 권한: {user.permission_groups}"
    )
    return user


async def get_admin_user(
    current_user: schemas.UserInDB = Depends(get_current_user),
) -> schemas.UserInDB:
    """
    현재 인증된 사용자가 'admin' 권한 그룹을 가지고 있는지 확인하는 의존성입니다.
    관리자 권한이 없으면 `HTTPException` (403 Forbidden)을 발생시킵니다.

    Args:
        current_user: `get_current_user`로부터 주입된 현재 사용자 정보.

    Returns:
        schemas.UserInDB: 관리자 권한이 확인된 사용자 정보.
    """
    if "admin" not in current_user.permission_groups:
        logger.warning(
            f"사용자 '{current_user.username}'가 관리자 전용 엔드포인트에 접근 시도 (권한 없음)."
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )
    logger.debug(f"관리자 접근 확인: 사용자 '{current_user.username}'")
    return current_user


# --- 속도 제한(Rate Limit) 의존성 ---


async def enforce_chat_rate_limit(
    current_user: schemas.UserInDB = Depends(get_current_user),
) -> None:
    """채팅 엔드포인트에 대한 사용자별 속도 제한을 강제합니다."""
    try:
        # `rate_limiter`는 사용자 ID를 기준으로 'chat' 유형의 요청 횟수를 확인합니다.
        await rate_limiter.assert_within_limit(
            "chat", str(current_user.user_id)
        )
        logger.debug(f"사용자 '{current_user.username}'의 채팅 속도 제한 통과.")
    except ValueError as exc:
        logger.warning(
            f"사용자 '{current_user.username}'가 채팅 속도 제한에 도달했습니다: {exc}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc


async def enforce_document_rate_limit(
    current_user: schemas.UserInDB = Depends(get_current_user),
) -> None:
    """문서 관련 엔드포인트에 대한 사용자별 속도 제한을 강제합니다."""
    try:
        await rate_limiter.assert_within_limit(
            "documents", str(current_user.user_id)
        )
        logger.debug(
            f"사용자 '{current_user.username}'의 문서 작업 속도 제한 통과."
        )
    except ValueError as exc:
        logger.warning(
            f"사용자 '{current_user.username}'가 문서 작업 속도 제한에 도달했습니다: {exc}"
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
