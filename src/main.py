import asyncio
import json
from contextlib import asynccontextmanager
from typing import List, Dict, Any, AsyncGenerator, Optional

import uvicorn
import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl

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
    get_vector_store,
    get_reranker,
    get_tools,
)

logger = get_logger(__name__)


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
        llm = get_llm(settings)
        vector_store = get_vector_store(settings, embedding_model)
        reranker = get_reranker(settings)
        tools = get_tools(settings)

        # AgentBrain을 모든 컴포넌트를 주입하여 초기화
        agent_brain = AgentBrain(
            settings=settings,
            llm=llm,
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


@app.post("/query/corporate")
async def query_corporate_core(request: Request, body: QueryRequest):
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
    cache_key = f"sentinel_cache:{body.query}:{sorted(body.permission_groups)}"

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

    inputs = {
        "question": body.query,
        "permission_groups": body.permission_groups,
        "top_k": body.top_k,
        "doc_ids_filter": body.doc_ids_filter,
    }
    return StreamingResponse(
        stream_agent_response(agent_brain, inputs, redis_client, cache_key),
        media_type="text/event-stream",
    )


@app.post("/upload-and-index")
async def upload_and_index_document(
    file: UploadFile = File(...),
    permission_groups_str: str = Form('["all_users"]'),
):
    """
    파일을 업로드받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    try:
        file_content = await file.read()
        permission_groups = json.loads(permission_groups_str)
        if not isinstance(permission_groups, list):
            raise ValueError("permission_groups는 반드시 리스트 형태여야 합니다.")

        # Celery 작업 호출
        process_document_indexing.delay(
            file_content=file_content,
            file_name=file.filename,
            permission_groups=permission_groups,
        )

        logger.info(f"'{file.filename}' 파일을 Celery에 인덱싱 작업으로 위임했습니다.")
        return {
            "status": "success",
            "filename": file.filename,
            "message": "파일 업로드 성공. 백그라운드에서 인덱싱이 시작되었습니다.",
        }
    except Exception as e:
        logger.error(f"파일 업로드 및 인덱싱 위임 중 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/documents")
async def get_indexed_documents(request: Request):
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
            from sqlalchemy import text

            # 'source' 메타데이터에서 파일 이름을 가져옵니다. (zip 파일의 경우 원본 zip 이름)
            stmt = text(
                """
                -- 1. 개별 파일 가져오기
                SELECT 
                    doc_id AS filter_key, 
                    metadata->>'source' AS display_name
                FROM documents
                WHERE metadata->>'source_type' = 'file-upload'
                
                UNION
                
                -- 2. ZIP 파일들 가져오기 (이름 기준 중복 제거)
                SELECT 
                    DISTINCT ON (metadata->>'original_zip')
                    'file-upload-' || (metadata->>'original_zip') || '/' AS filter_key,
                    metadata->>'original_zip' AS display_name
                FROM documents
                WHERE metadata->>'source_type' = 'file-upload-zip'
                
                ORDER BY display_name
                
                -- 3. GitHub 레포들 가져오기 (이름 기준 중복 제거)
                SELECT 
                    DISTINCT ON (metadata->>'repo_name')
                    'github-repo-' || (metadata->>'repo_name') || '/' AS filter_key,
                    metadata->>'repo_name' AS display_name
                FROM documents
                WHERE metadata->>'source_type' = 'github-repo'
                
                ORDER BY display_name
            """
            )
            result = await session.execute(stmt)

            documents = {row.filter_key: row.display_name for row in result}
            return documents
    except Exception as e:
        logger.error(f"인덱싱된 문서 조회 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"문서 조회 실패: {e}")


@app.post("/index-github-repo")
async def index_github_repo(body: GitHubRepoRequest):
    """
    GitHub 저장소 URL을 받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    try:
        process_github_repo_indexing.delay(
            repo_url=str(body.repo_url),  # Pydantic 모델을 문자열로 변환
            permission_groups=body.permission_groups,
        )

        repo_name = str(body.repo_url).split("/")[-1].replace(".git", "")
        logger.info(f"'{repo_name}' 저장소를 Celery에 인덱싱 작업으로 위임했습니다.")
        return {
            "status": "success",
            "repo_name": repo_name,
            "message": "GitHub 저장소 클론 및 인덱싱이 백그라운드에서 시작되었습니다.",
        }
    except Exception as e:
        logger.error(f"GitHub 인덱싱 위임 중 에러 발생: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- 6. 서버 실행 ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
