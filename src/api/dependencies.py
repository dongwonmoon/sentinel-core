"""
FastAPI 의존성 주입 시스템을 위한 "제공자(Provider)" 함수들을 정의합니다.
"""

from functools import lru_cache
from typing import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ..core import factories
from ..core.agent import Agent
from ..core.config import Settings
from ..core.security import verify_token
from ..components.embeddings.base import BaseEmbeddingModel
from ..components.vector_stores.base import BaseVectorStore
from ..components.vector_stores.pg_vector_store import PgVectorStore
from . import schemas

# --- 핵심 컴포넌트 제공자 ---


@lru_cache
def get_settings() -> Settings:
    """설정 객체를 반환합니다. lru_cache를 통해 앱 전체에서 싱글톤으로 동작합니다."""
    from ..core.config import settings

    return settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


@lru_cache
def get_agent() -> Agent:
    """
    모든 컴포넌트를 생성하고 조립하여 Agent 인스턴스를 반환합니다.
    lru_cache를 통해 앱 전체에서 싱글톤으로 동작하여, 비싼 객체 생성을 한 번만 수행합니다.
    """
    settings = get_settings()

    # 1. 핵심 컴포넌트 생성
    embedding_model = factories.create_embedding_model(
        settings.embedding, settings.OPENAI_API_KEY
    )
    vector_store = factories.create_vector_store(
        settings.vector_store, settings, embedding_model
    )
    fast_llm = factories.create_llm(settings.llm.fast, settings.OPENAI_API_KEY)
    powerful_llm = factories.create_llm(
        settings.llm.powerful,
        settings.POWERFUL_OLLAMA_API_KEY or settings.OPENAI_API_KEY,
    )
    reranker = factories.create_reranker(
        settings.reranker, settings.COHERE_API_KEY
    )
    tools = factories.get_tools(settings.tools_enabled)

    # 2. Agent 인스턴스화
    return Agent(
        fast_llm=fast_llm,
        powerful_llm=powerful_llm,
        vector_store=vector_store,
        reranker=reranker,
        tools=tools,
    )


# --- 요청 단위(Request-scoped) 제공자 ---


async def get_db_session(
    # get_agent를 호출하면 캐시된 Agent 인스턴스가 반환됩니다.
    # 이 인스턴스에서 vector_store를 가져와 DB 세션을 생성합니다.
    agent: Agent = Depends(get_agent),
) -> AsyncGenerator[AsyncSession, None]:
    """요청마다 DB 세션을 생성하고, 요청 완료 후 닫는 의존성."""
    vector_store = agent.vector_store
    if not isinstance(vector_store, PgVectorStore):
        raise HTTPException(
            status_code=500,
            detail="Database session is only available for PgVectorStore.",
        )

    session_local = vector_store.AsyncSessionLocal
    if not session_local:
        raise HTTPException(
            status_code=500, detail="DB session factory is not initialized."
        )

    session: AsyncSession = session_local()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> schemas.UserInDB:
    """JWT 토큰을 검증하고, DB에서 최신 사용자 정보를 조회하여 반환합니다."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = verify_token(token, credentials_exception)

    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": token_data.username})
    user_row = result.fetchone()

    if user_row is None:
        raise credentials_exception

    user = schemas.UserInDB(**user_row._asdict())
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user
