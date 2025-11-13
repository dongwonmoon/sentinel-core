"""
FastAPI 의존성 주입 시스템을 위한 "제공자(Provider)" 함수들을 정의합니다.
이 함수들은 엔드포인트 함수들의 시그니처에 `Depends()`와 함께 사용됩니다.
"""
from functools import lru_cache
from typing import AsyncGenerator, List

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

# --- 1. 아키텍처에 따른 모듈 임포트 ---
from ..core import factories
from ..core.agent import Agent
from ..core.config import Settings, LLMSettings, EmbeddingSettings, VectorStoreSettings, RerankerSettings
from ..core.security import verify_token
from ..components.embeddings.base import BaseEmbeddingModel
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.vector_stores.base import BaseVectorStore
from ..components.vector_stores.pg_vector_store import PgVectorStore
from ..components.tools.base import BaseTool
from . import schemas


# --- 2. 핵심 컴포넌트 제공자 ---

@lru_cache
def get_settings() -> Settings:
    """설정 객체를 반환합니다. lru_cache를 통해 앱 전체에서 싱글톤으로 동작합니다."""
    from ..core.config import settings
    return settings

# OAuth2 스킴 정의 (tokenUrl은 auth 엔드포인트의 경로)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_embedding_model(settings: Settings = Depends(get_settings)) -> BaseEmbeddingModel:
    """설정에 맞는 임베딩 모델 인스턴스를 생성하여 반환합니다."""
    return factories.create_embedding_model(
        embedding_settings=settings.embedding,
        openai_api_key=settings.OPENAI_API_KEY,
    )

def get_vector_store(
    settings: Settings = Depends(get_settings),
    embedding_model: BaseEmbeddingModel = Depends(get_embedding_model),
) -> BaseVectorStore:
    """설정에 맞는 벡터 스토어 인스턴스를 생성하여 반환합니다."""
    return factories.create_vector_store(
        vs_settings=settings.vector_store,
        full_settings=settings,
        embedding_model=embedding_model,
    )

@lru_cache
def get_agent(
    settings: Settings = Depends(get_settings),
) -> Agent:
    """
    모든 컴포넌트를 조립하여 Agent 인스턴스를 생성합니다.
    lru_cache를 통해 앱 전체에서 싱글톤으로 동작합니다.
    """
    # 각 컴포넌트 생성
    fast_llm = factories.create_llm(settings.llm.fast, settings.OPENAI_API_KEY)
    powerful_llm = factories.create_llm(settings.llm.powerful, settings.POWERFUL_OLLAMA_API_KEY or settings.OPENAI_API_KEY)
    reranker = factories.create_reranker(settings.reranker, settings.COHERE_API_KEY)
    tools = factories.get_tools(settings.tools_enabled)
    
    # Vector Store는 별도 의존성으로 주입받아 Agent를 생성할 수도 있지만,
    # Agent가 강하게 의존하는 핵심 컴포넌트이므로 내부에서 생성하는 것도 합리적입니다.
    embedding_model = get_embedding_model(settings)
    vector_store = get_vector_store(settings, embedding_model)

    return Agent(
        fast_llm=fast_llm,
        powerful_llm=powerful_llm,
        vector_store=vector_store,
        reranker=reranker,
        tools=tools,
    )


# --- 3. 요청 단위(Request-scoped) 제공자 ---

async def get_db_session(
    vector_store: BaseVectorStore = Depends(get_vector_store),
) -> AsyncGenerator[AsyncSession, None]:
    """
    요청마다 DB 세션을 생성하고, 요청 완료 후 닫는 의존성.
    PgVectorStore가 초기화한 세션 메이커를 사용합니다.
    """
    if not isinstance(vector_store, PgVectorStore):
        raise HTTPException(
            status_code=500,
            detail="Database session is only available for PgVectorStore."
        )
    
    session_local = vector_store.AsyncSessionLocal
    if not session_local:
        raise HTTPException(status_code=500, detail="DB session factory is not initialized.")

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
    """
    JWT 토큰을 검증하고, DB에서 최신 사용자 정보를 조회하여 반환하는 핵심 의존성.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token_data = verify_token(token, credentials_exception)
    
    from sqlalchemy import text
    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": token_data.username})
    user_row = result.fetchone()

    if user_row is None:
        raise credentials_exception
        
    user = schemas.UserInDB(**user_row._asdict())
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
        
    return user
