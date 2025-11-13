import asyncio
import json
from contextlib import asynccontextmanager
from typing import List, Dict, Any, AsyncGenerator, Optional, Literal
from datetime import datetime

import uvicorn
import redis.asyncio as redis
from fastapi import (
    FastAPI,
    HTTPException,
    File,
    UploadFile,
    Form,
    Request,
    Depends,
    status,
)
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# --- 1. 설정 및 추상화 모듈 임포트 ---
from .agent_brain import AgentBrain
from .config import Settings, settings
from .embeddings.base import BaseEmbeddingModel
from .embeddings.ollama import OllamaEmbedding
from .embeddings.openai import OpenAIEmbedding
from .llms.base import BaseLLM
from .llms.ollama import OllamaLLM
from .llms.openai import OpenAILLM
from .rerankers.base import BaseReranker
from .rerankers.noop_reranker import NoOpReranker
from .store.base import BaseVectorStore
from .store.pg_vector_store import PgVectorStore
from .store.milvus_vector_store import MilvusVectorStore
from .tasks import process_document_indexing, process_github_repo_indexing
from .tools.base import BaseTool
from .tools.duckduckgo_search import get_duckduckgo_search_tool
from .tools.code_execution import get_code_execution_tool
from .logger import get_logger
from .factories import (
    get_embedding_model,
    get_llm,
    get_powerful_llm,
    get_vector_store,
    get_reranker,
    get_tools,
)
from . import auth

logger = get_logger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- 2. FastAPI Lifespan 및 앱 초기화 ---


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 앱의 시작과 종료 시점에 실행될 로직을 정의합니다. (Lifespan 이벤트)
    앱 시작 시 모든 핵심 컴포넌트를 동적으로 초기화하고 app.state에 저장합니다.
    """
    logger.info("--- [FastAPI Lifespan] 앱 시작: 컴포넌트 초기화 시작 ---")
    app.state.agent_brain = None
    app.state.redis_client = None

    try:
        # 팩토리 함수를 사용하여 설정에 따라 각 컴포넌트의 실제 구현체를 생성
        embedding_model = get_embedding_model(settings)
        llm_fast = get_llm(settings)
        llm_powerful = get_powerful_llm(settings)
        vector_store = get_vector_store(settings, embedding_model)
        reranker = get_reranker(settings)
        tools = get_tools(settings)

        # AgentBrain을 모든 컴포넌트를 주입하여 초기화
        agent_brain = AgentBrain(
            settings=settings,
            llm=llm_fast,
            powerful_llm=llm_powerful,
            vector_store=vector_store,
            reranker=reranker,
            tools=tools,
        )
        # 초기화된 brain을 app.state에 저장하여 API 엔드포인트에서 사용
        app.state.agent_brain = agent_brain

        try:
            redis_client = redis.from_url(
                settings.CELERY_BROKER_URL, decode_responses=True
            )
            await redis_client.ping()
            app.state.redis_client = redis_client
            logger.info(f"--- [FastAPI Lifespan] Redis 연결 성공 ---")
        except Exception as e:
            logger.error(
                f"--- [FastAPI Lifespan] Redis 연결 실패: {e} ---",
                exc_info=True,
            )

        logger.info(
            "--- [FastAPI Lifespan] 모든 컴포넌트 및 AgentBrain 초기화 완료 ---"
        )
        yield
    except Exception as e:
        logger.error(f"--- [FastAPI Lifespan] 초기화 실패: {e} ---", exc_info=True)
        # 앱 시작을 막기 위해 예외를 다시 발생시킬 수 있습니다。
        raise
    finally:
        if app.state.redis_client:
            await app.state.redis_client.close()
            logger.info("--- [FastAPI Lifespan] Redis 연결 종료 ---")
        # 앱 종료 시 실행될 클린업 로직 (필요 시)
        logger.info("--- [FastAPI Lifespan] 앱 종료 ---")


app = FastAPI(
    title=settings.APP_TITLE,
    description=settings.APP_DESCRIPTION,
    version="0.2.0",  # 버전 업데이트
    lifespan=lifespan,
)


# --- 4. API 요청/응답 모델 ---


class ChatMessageBase(BaseModel):
    """채팅 메시지의 기본 스키마"""

    role: Literal["user", "assistant"]
    content: str


class ChatMessageHistory(ChatMessageBase):
    """DB에서 읽어올 때 사용할 스키마 (생성 시간 포함)"""

    created_at: datetime

    class Config:
        orm_mode = True  # SQLAlchemy 모델과 호환


class ChatHistoryResponse(BaseModel):
    """GET /chat-history 응답 스키마"""

    messages: List[ChatMessageHistory]


class QueryRequest(BaseModel):
    """API가 받을 요청 본문의 형태를 정의합니다."""

    query: str = Field(..., description="사용자의 질문")
    permission_groups: List[str] = Field(
        default=["all_users"], description="사용자의 권한 그룹"
    )
    top_k: int = Field(default=3, description="RAG 검색 시 반환할 최종 청크 수")
    doc_ids_filter: Optional[List[str]] = Field(
        default=None, description="RAG 검색을 제한할 문서 ID 리스트"
    )
    chat_history: Optional[List[ChatMessageBase]] = Field(
        default=None, description="이전 대화 기록"
    )


class GitHubRepoRequest(BaseModel):
    repo_url: HttpUrl = Field(..., description="인덱싱할 GitHub 저장소의 URL")
    permission_groups: List[str] = Field(
        default=["all_users"], description="사용자의 권한 그룹"
    )


class Source(BaseModel):
    """답변의 출처 정보를 담는 모델"""

    page_content: str
    metadata: Dict[str, Any]
    score: float


class DeleteDocumentRequest(BaseModel):
    """DELETE /documents 요청 본문 스키마"""

    doc_id_or_prefix: str = Field(..., description="삭제할 doc_id 또는 접두사")


# --- 5. API 엔드포인트 ---


async def stream_agent_response(
    agent_brain: AgentBrain,
    inputs: Dict[str, Any],
    redis_client: Optional[redis.Redis],
    cache_key: str,
) -> AsyncGenerator[str, None]:
    """LangGraph 스트림(astream_events)을 받아 SSE(Server-Sent Events)로 변환합니다."""

    final_state = None
    full_response = ""

    # astream_events는 LangGraph의 각 노드 실행 전/후 이벤트를 스트리밍합니다.
    async for event in agent_brain.graph_app.astream_events(inputs, version="v1"):
        kind = event["event"]

        # 'on_chat_model_stream' 이벤트는 LLM에서 생성되는 토큰 스트림입니다.
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                # 클라이언트에 'token' 이벤트 전송
                yield f"data: {json.dumps({'event': 'token', 'data': content})}\n\n"

        # 'on_tool_end' 이벤트는 도구 실행이 끝났을 때 발생합니다.
        if kind == "on_tool_end":
            # 최종 상태를 저장해 둡니다.
            final_state = event["data"].get("output")

    final_data_to_cache = {}

    # 스트리밍이 모두 끝난 후, 최종 상태에서 출처 정보를 추출하여 전송합니다.
    if final_state and isinstance(final_state, dict):
        tool_outputs = final_state.get("tool_outputs", {})
        rag_chunks = tool_outputs.get("rag_chunks", [])

        sources = [Source(**chunk) for chunk in rag_chunks]
        sources_dict = [s.dict() for s in sources]

        # 클라이언트에 'sources' 이벤트 전송
        yield f"data: {json.dumps({'event': 'sources', 'data': sources_dict})}\n\n"

        search_result = tool_outputs.get("search_result", "")
        code_input = final_state.get("code_input", "")
        code_result = tool_outputs.get("code_result", "")

        if search_result:
            yield f"data: {json.dumps({'event': 'search_result', 'data': search_result})}\n\n"
        if code_result or code_input:
            yield f"data: {json.dumps({'event': 'code_result', 'data': {'input': code_input, 'output': code_result}})}\n\n"

        final_data_to_cache = {
            "full_response": full_response,
            "sources": sources_dict,
            "search_result": search_result,
            "code_result": {"input": code_input, "output": code_result},
        }

    if redis_client and final_data_to_cache:
        try:
            await redis_client.set(cache_key, json.dumps(final_data_to_cache))
            logger.info(f"--- [Cache] SET: {cache_key}")
        except Exception as e:
            logger.error(f"--- [Cache] SET 실패: {e} ---", exc_info=True)

    yield f"data: {json.dumps({'event': 'end'})}\n\n"


async def stream_cached_response(
    cached_data: dict,
) -> AsyncGenerator[str, None]:
    """캐시된 데이터를 SSE 스트림 형식으로 즉시 반환합니다."""

    logger.debug("--- [Cache] Streaming cached response ---")

    # 1. 캐시된 전체 답변을 'token' 이벤트로 한 번에 전송
    full_response = cached_data.get("full_response", "")
    if full_response:
        yield f"data: {json.dumps({'event': 'token', 'data': full_response})}\n\n"

    # 2. 캐시된 출처(sources) 전송
    sources = cached_data.get("sources", [])
    if sources:
        yield f"data: {json.dumps({'event': 'sources', 'data': sources})}\n\n"

    # 3. 캐시된 웹 검색 결과(search_result) 전송
    search_result = cached_data.get("search_result", "")
    if search_result:
        yield f"data: {json.dumps({'event': 'search_result', 'data': search_result})}\n\n"

    # 4. 캐시된 코드 실행 결과(code_result) 전송
    code_result = cached_data.get("code_result", {})
    if code_result and (code_result.get("input") or code_result.get("output")):
        yield f"data: {json.dumps({'event': 'code_result', 'data': code_result})}\n\n"

    # 5. 스트림 종료 이벤트 전송
    yield f"data: {json.dumps({'event': 'end'})}\n\n"


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """
    요청마다 DB 세션을 생성하고, 완료되면 닫는 FastAPI 의존성.
    PgVectorStore가 초기화한 세션 메이커를 사용합니다.
    """
    session_local = request.app.state.agent_brain.vector_store.AsyncSessionLocal
    if not session_local:
        raise HTTPException(
            status_code=500, detail="DB 세션 풀이 초기화되지 않았습니다."
        )

    session: AsyncSession = session_local()
    logger.info("--- [DB] 트랜잭션 시작 ---")

    try:
        yield session  # 엔드포인트 실행
        logger.info("--- [DB] 트랜잭션 커밋 시도 ---")
        await session.commit()
        logger.info("--- [DB] 트랜잭션 커밋 완료 ---")

    except Exception as e:
        logger.error(f"--- [DB] 예외 발생, 트랜잭션 롤백: {e} ---", exc_info=True)
        await session.rollback()
        raise e  # 오류를 FastAPI로 다시 전달
    finally:
        logger.info("--- [DB] 세션 닫기 ---")
        await session.close()


async def get_user_from_db(
    session: AsyncSession, username: str
) -> Optional[auth.UserInDB]:
    """DB에서 사용자 정보를 조회합니다."""
    stmt = text("SELECT * FROM users WHERE username = :username")
    result = await session.execute(stmt, {"username": username})
    user_row = result.fetchone()
    if user_row:
        return auth.UserInDB(**user_row._asdict())  # Row를 Pydantic 모델로 변환
    return None


async def get_current_user(
    token: str = Depends(oauth2_scheme), session: AsyncSession = Depends(get_db_session)
) -> auth.UserInDB:
    """
    JWT 토큰을 검증하고, DB에서 최신 사용자 정보를 반환하는 핵심 의존성.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="자격 증명을 검증할 수 없습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = auth.verify_token(token, credentials_exception)

    user = await get_user_from_db(session, token_data.username)
    if user is None or not user.is_active:
        raise credentials_exception
    return user


@app.post("/register", response_model=auth.User, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_create: auth.UserCreate, session: AsyncSession = Depends(get_db_session)
):
    """
    신규 사용자 등록 (회원가입).
    (MVP: 우선은 누구나 가입 가능하게 둠)
    """
    db_user = await get_user_from_db(session, user_create.username)
    if db_user:
        raise HTTPException(...)

    hashed_password = auth.get_password_hash(user_create.password)

    stmt = text("""...""")
    try:
        new_user_row = (await session.execute(stmt, {...})).fetchone()
    except Exception as e:
        logger.error(f"User INSERT 실패: {e}")
        raise HTTPException(...)

    if not new_user_row:
        raise HTTPException(...)

    return auth.User(**new_user_row._asdict())


@app.post("/token", response_model=auth.Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_db_session),
):
    """
    사용자 로그인 (JWT 토큰 발급).
    FastAPI의 OAuth2PasswordRequestForm을 사용하여 'application/x-www-form-urlencoded'로 요청받음.
    """
    user = await get_user_from_db(session, form_data.username)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="사용자 이름 또는 비밀번호가 올바르지 않습니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 토큰에 username과 실제 권한 그룹을 저장
    access_token_data = {
        "sub": user.username,
        "permission_groups": user.permission_groups,
    }
    access_token = auth.create_access_token(data=access_token_data)

    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/chat-history", response_model=ChatHistoryResponse)
async def get_chat_history(
    current_user: auth.UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    현재 로그인한 사용자의 모든 채팅 기록을 시간순으로 가져옵니다.
    """
    stmt = text(
        """
        SELECT role, content, created_at 
        FROM chat_history
        WHERE user_id = :user_id 
        ORDER BY created_at ASC
    """
    )
    result = await session.execute(stmt, {"user_id": current_user.user_id})
    messages = [
        ChatMessageHistory(
            role=row.role, content=row.content, created_at=row.created_at
        )
        for row in result
    ]
    return ChatHistoryResponse(messages=messages)


@app.post("/chat-message", status_code=status.HTTP_201_CREATED)
async def save_chat_message(
    message: ChatMessageBase,
    current_user: auth.UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """
    'user' 또는 'assistant'의 단일 메시지를 DB에 저장합니다.
    """

    try:
        stmt = text(
            """
            INSERT INTO chat_history (user_id, role, content)
            VALUES (:user_id, :role, :content)
        """
        )

        logger.info(f"--- [CHAT_SAVE] INSERT 실행 (User: {current_user.user_id}) ---")
        await session.execute(
            stmt,
            {
                "user_id": current_user.user_id,
                "role": message.role,
                "content": message.content,
            },
        )
        logger.info(f"--- [CHAT_SAVE] INSERT 완료 ---")

    except Exception as e:
        logger.error(f"--- [CHAT_SAVE] INSERT 실패: {e} ---", exc_info=True)
        raise e  # 예외를 get_db_session으로 전달하여 롤백

    return {"status": "message saved"}


@app.post("/query/corporate")
async def query_corporate_core(
    request: Request,
    body: QueryRequest,
    current_user: auth.UserInDB = Depends(get_current_user),
):
    """
    LangGraph 에이전트의 답변을 스트리밍 방식으로 반환합니다.
    """
    agent_brain = request.app.state.agent_brain
    redis_client = request.app.state.redis_client

    if not agent_brain:
        raise HTTPException(
            status_code=500,
            detail="서버 컴포넌트(AgentBrain)가 로드되지 않았습니다.",
        )

    filter_key = ":".join(sorted(body.doc_ids_filter)) if body.doc_ids_filter else "all"
    user_perms_key = ":".join(sorted(current_user.permission_groups))
    cache_key = f"sentinel_cache:{body.query}:{user_perms_key}:{filter_key}"

    if redis_client:
        try:
            cached_data_json = await redis_client.get(cache_key)
            if cached_data_json:
                logger.info(f"--- [Cache] HIT: {cache_key}")
                cached_data = json.loads(cached_data_json)
                return StreamingResponse(
                    stream_cached_response(cached_data),
                    media_type="text/event-stream",
                )
        except Exception as e:
            logger.error(f"--- [Cache] GET 실패: {e} ---", exc_info=True)

    logger.info(f"--- [Cache] MISS: {cache_key} ---")

    chat_history_dicts = []
    if body.chat_history:
        chat_history_dicts = [msg.dict() for msg in body.chat_history]

    inputs = {
        "question": body.query,
        "permission_groups": current_user.permission_groups,
        "top_k": body.top_k,
        "doc_ids_filter": body.doc_ids_filter,
        "chat_history": chat_history_dicts,
    }
    return StreamingResponse(
        stream_agent_response(agent_brain, inputs, redis_client, cache_key),
        media_type="text/event-stream",
    )


@app.post("/upload-and-index")
async def upload_and_index_document(
    file: UploadFile = File(...),
    permission_groups_str: str = Form('["all_users"]'),
    current_user: auth.UserInDB = Depends(get_current_user),
):
    """
    파일을 업로드받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    try:
        file_content = await file.read()
        user_permission_groups = current_user.permission_groups
        if not user_permission_groups:
            user_permission_groups = ["all_users"]

        process_document_indexing.delay(
            file_content=file_content,
            file_name=file.filename,
            permission_groups=user_permission_groups,  # 실제 사용자 권한 전달
        )

        logger.info(
            f"'{file.filename}' 파일을 Celery에 위임 (User: {current_user.username}, Groups: {user_permission_groups})"
        )
        return {
            "status": "success",
            "filename": file.filename,
            "message": "파일 업로드 성공. 백그라운드에서 인덱싱이 시작되었습니다.",
        }
    except Exception as e:
        logger.error(f"파일 업로드 및 인덱싱 위임 중 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def get_indexed_documents(
    request: Request, current_user: auth.UserInDB = Depends(get_current_user)
):
    """
    현재 인덱싱된 모든 문서의 doc_id와 파일 이름을 반환합니다.
    """
    agent_brain = request.app.state.agent_brain
    if not agent_brain or not isinstance(agent_brain.vector_store, PgVectorStore):
        raise HTTPException(
            status_code=500,
            detail="Vector store (PgVectorStore)가 로드되지 않았습니다.",
        )

    session_local = agent_brain.vector_store.AsyncSessionLocal

    try:
        async with session_local() as session:

            # 'source' 메타데이터에서 파일 이름을 가져옵니다. (zip 파일의 경우 원본 zip 이름)
            stmt = text(
                """
                WITH FilteredDocs AS (
                    SELECT DISTINCT 
                        doc_id,
                        metadata->>'source' AS source_name,
                        metadata->>'original_zip' AS zip_name,
                        metadata->>'repo_name' AS repo_name,
                        metadata->>'source_type' AS source_type
                    FROM documents d
                    WHERE d.permission_groups && :allowed_groups -- [보안 필터]
                )
                -- 1. 개별 파일
                SELECT 
                    doc_id AS filter_key, 
                    source_name AS display_name
                FROM FilteredDocs
                WHERE source_type = 'file-upload'
                
                UNION
                
                -- 2. ZIP 파일들
                SELECT 
                    'file-upload-' || zip_name || '/' AS filter_key,
                    zip_name AS display_name
                FROM FilteredDocs
                WHERE source_type = 'file-upload-zip' AND zip_name IS NOT NULL
                
                UNION

                -- 3. GitHub 레포들
                SELECT 
                    'github-repo-' || repo_name || '/' AS filter_key,
                    repo_name AS display_name
                FROM FilteredDocs
                WHERE source_type = 'github-repo' AND repo_name IS NOT NULL
                
                ORDER BY display_name
            """
            )
            result = await session.execute(
                stmt, {"allowed_groups": current_user.permission_groups}
            )

            documents = {row.filter_key: row.display_name for row in result}
            return documents

    except Exception as e:
        logger.error(f"인덱싱된 문서 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"문서 조회 실패: {e}")


@app.post("/index-github-repo")
async def index_github_repo(
    body: GitHubRepoRequest, current_user: auth.UserInDB = Depends(get_current_user)
):
    """
    GitHub 저장소 URL을 받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    try:
        user_permission_groups = current_user.permission_groups
        if not user_permission_groups:
            user_permission_groups = ["all_users"]

        process_github_repo_indexing.delay(
            repo_url=str(body.repo_url),
            permission_groups=user_permission_groups,  # 실제 사용자 권한 전달
        )

        repo_name = str(body.repo_url).split("/")[-1].replace(".git", "")
        logger.info(
            f"'{repo_name}' 저장소를 Celery에 위임 (User: {current_user.username}, Groups: {user_permission_groups})"
        )
        return {
            "status": "success",
            "repo_name": repo_name,
            "message": "GitHub 저장소 클론 및 인덱싱이 백그라운드에서 시작되었습니다.",
        }
    except Exception as e:
        logger.error(f"GitHub 인덱싱 위임 중 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/documents", status_code=status.HTTP_200_OK)
async def delete_indexed_document(
    body: DeleteDocumentRequest,
    request: Request,  # AgentBrain(VectorStore) 접근을 위해
    current_user: auth.UserInDB = Depends(get_current_user),
):
    """
    인덱싱된 지식 소스(파일, ZIP, 레포)를 삭제합니다.
    사용자에게 해당 문서를 삭제할 권한(permission_groups)이 있어야 합니다.
    """
    try:
        agent_brain = request.app.state.agent_brain
        if not agent_brain or not isinstance(agent_brain.vector_store, PgVectorStore):
            raise HTTPException(
                status_code=500,
                detail="Vector store (PgVectorStore)가 로드되지 않았습니다.",
            )

        deleted_count = await agent_brain.vector_store.delete_documents(
            doc_id_or_prefix=body.doc_id_or_prefix,
            permission_groups=current_user.permission_groups,  # [보안]
        )

        if deleted_count > 0:
            return {
                "status": "success",
                "message": f"'{body.doc_id_or_prefix}' 관련 문서 {deleted_count}개 삭제 완료.",
            }
        else:
            # 삭제할 문서가 없거나 (이미 삭제됨), 권한이 없는 경우
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="삭제할 문서를 찾지 못했거나, 해당 문서에 대한 삭제 권한이 없습니다.",
            )

    except Exception as e:
        logger.error(f"문서 삭제 중 에러 발생: {e}", exc_info=True)
        # 이미 HTTP 예외인 경우 그대로 전달
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"문서 삭제 실패: {e}")


# --- 6. 서버 실행 ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
