# -*- coding: utf-8 -*-
"""
API 라우터: 채팅 (Chat)

이 모듈은 사용자와 RAG 에이전트 간의 상호작용을 위한 모든 API 엔드포인트를 정의합니다.
-   **/query**: 사용자의 질문을 받아 실시간으로 답변을 스트리밍합니다.
-   **/sessions**: 사용자의 이전 채팅 세션 목록을 조회합니다.
-   **/history/{session_id}**: 특정 채팅 세션의 대화 기록을 조회합니다.
-   **/profile**: 사용자의 프로필 정보를 조회하고 업데이트합니다.
"""
import json
import redis.asyncio as aioredis

from fastapi import APIRouter, BackgroundTasks, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import dependencies, schemas
from ...core.agent import Agent
from ...core.logger import get_logger
from ...services import chat_service

# 'chat' 기능에 대한 API 라우터를 생성합니다.
# 이 라우터에 등록된 모든 엔드포인트는 '/api/chat' 접두사를 갖게 됩니다.
router = APIRouter()
logger = get_logger(__name__)


@router.post("/query", summary="에이전트에게 실시간 쿼리")
async def query_agent(
    body: schemas.QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _: None = Depends(dependencies.enforce_chat_rate_limit),
    agent: Agent = Depends(dependencies.get_agent),
    db_session: AsyncSession = Depends(dependencies.get_db_session),
    redis: aioredis.Redis = Depends(dependencies.get_redis_client),
) -> StreamingResponse:
    """
    에이전트에게 질문(Query)을 보내고, 답변을 실시간 스트리밍 방식으로 반환합니다.

    이 엔드포인트는 Server-Sent Events (SSE)를 사용하여 클라이언트에게 지속적으로
    데이터 조각(토큰)을 전송합니다. 이를 통해 사용자는 챗봇의 답변이 생성되는 과정을
    실시간으로 볼 수 있습니다.

    대화 내용은 `background_tasks`를 통해 요청-응답 사이클이 끝난 후
    백그라운드에서 비동기적으로 데이터베이스에 저장됩니다.

    Args:
        body (schemas.QueryRequest): 사용자의 질문, 대화 기록, 세션 ID 등을 포함하는 요청 본문.
        background_tasks (BackgroundTasks): FastAPI가 제공하는 백그라운드 작업 관리자.
        current_user (schemas.UserInDB): `get_current_user` 의존성을 통해 주입된, 인증된 사용자 정보.
        _ (None): `enforce_chat_rate_limit` 의존성을 실행하지만, 그 반환값은 사용하지 않음.
        agent (Agent): `get_agent` 의존성을 통해 주입된, 캐시된 싱글톤 에이전트 인스턴스.

    Returns:
        StreamingResponse: 'text/event-stream' MIME 타입을 가진 스트리밍 응답.
    """
    logger.info(
        f"사용자 '{current_user.username}'(ID: {current_user.user_id})로부터 "
        f"세션 '{body.session_id}'에 대한 쿼리 수신: '{body.query[:100]}...'"
    )

    # 에이전트(LangGraph)의 입력으로 사용될 딕셔너리를 구성합니다.
    # 사용자의 권한 그룹, 프로필 정보 등을 포함하여 개인화된 답변을 생성하는 데 사용됩니다.
    try:
        inputs = await chat_service.build_stateful_agent_inputs(
            redis=redis,
            db_session=db_session,
            user_id=current_user.user_id,
            session_id=body.session_id,
            query=body.query,
            top_k=body.top_k,
            permission_groups=current_user.permission_groups,
            user_profile=current_user.profile_text or "",
        )
    except Exception as e:
        logger.error(
            f"세션 '{body.session_id}'의 상태 저장 컨텍스트 빌드 실패: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build agent context.",
        )
    logger.debug(
        f"세션 '{body.session_id}'에 대한 에이전트 입력 데이터 구성 완료."
    )

    # `chat_service.stream_agent_response`는 비동기 제너레이터(Async Generator)를 반환합니다.
    # FastAPI는 이 제너레이터로부터 생성되는 데이터 조각들을 클라이언트로 스트리밍합니다.
    response_generator = chat_service.stream_agent_response(
        agent=agent,
        inputs=inputs,
        background_tasks=background_tasks,
        user_id=current_user.user_id,
        session_id=body.session_id,
    )

    return StreamingResponse(response_generator, media_type="text/event-stream")


@router.put(
    "/sessions/{session_id}/context",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_session_context(
    session_id: str,
    body: schemas.SessionContextUpdate,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    redis: aioredis.Redis = Depends(dependencies.get_redis_client),
):
    """
    채팅 세션의 상태(예: RAG 문서 필터)를 서버(Redis)에 저장(Stateful)합니다.
    프론트엔드가 RAG 필터를 변경할 때 이 API를 호출합니다.
    """
    logger.info(
        f"세션 '{session_id}' (사용자: '{current_user.username}')의 컨텍스트 업데이트 시도."
    )
    session_key = f"session_context:{session_id}"

    try:
        # 기존 컨텍스트를 읽어옵니다. (없으면 빈 객체)
        existing_context_raw = await redis.get(session_key)
        if existing_context_raw:
            context = json.loads(existing_context_raw)
        else:
            context = {}

        # 새 컨텍스트(doc_ids_filter)로 덮어씁니다.
        context["doc_ids_filter"] = body.doc_ids_filter

        # Redis에 (24시간 만료) 저장합니다.
        await redis.set(
            session_key, json.dumps(context), ex=86400
        )  # 24h expiry

        logger.debug(
            f"세션 컨텍스트 업데이트 완료: '{session_key}' = {context}"
        )
        return None  # 204 응답

    except Exception as e:
        logger.error(
            f"세션 '{session_id}'의 컨텍스트 업데이트 실패: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session context.",
        )


@router.get(
    "/sessions",
    response_model=schemas.ChatSessionListResponse,
    summary="사용자 채팅 세션 목록 조회",
)
async def get_chat_sessions(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> schemas.ChatSessionListResponse:
    """
    현재 인증된 사용자의 모든 채팅 세션 목록을 최신순으로 반환합니다.

    Args:
        current_user: 인증된 사용자 정보.
        session: DB 작업을 위한 비동기 세션.

    Returns:
        schemas.ChatSessionListResponse: 채팅 세션 목록을 포함하는 응답.
    """
    logger.info(
        f"사용자 '{current_user.username}'의 채팅 세션 목록 조회를 시작합니다."
    )
    sessions = await chat_service.fetch_user_sessions(
        db_session=session, user_id=current_user.user_id
    )
    logger.info(
        f"사용자 '{current_user.username}'의 세션 {len(sessions)}개를 성공적으로 조회했습니다."
    )
    return schemas.ChatSessionListResponse(sessions=sessions)


@router.get(
    "/history/{session_id}",
    response_model=schemas.ChatHistoryResponse,
    summary="특정 세션의 대화 기록 조회",
)
async def get_chat_history(
    session_id: str,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> schemas.ChatHistoryResponse:
    """
    특정 세션 ID에 해당하는 대화 기록을 시간순으로 정렬하여 반환합니다.
    사용자는 자신의 대화 기록만 조회할 수 있습니다.

    Args:
        session_id (str): 조회할 채팅 세션의 UUID.
        current_user: 인증된 사용자 정보.
        session: DB 작업을 위한 비동기 세션.

    Returns:
        schemas.ChatHistoryResponse: 대화 메시지 목록을 포함하는 응답.
    """
    logger.info(
        f"사용자 '{current_user.username}'가 세션 '{session_id}'의 대화 기록 조회를 요청했습니다."
    )
    messages = await chat_service.fetch_chat_history(
        db_session=session, user_id=current_user.user_id, session_id=session_id
    )
    logger.info(
        f"사용자 '{current_user.username}'의 세션 '{session_id}'에서 메시지 {len(messages)}개를 조회했습니다."
    )
    return schemas.ChatHistoryResponse(messages=messages)


@router.get(
    "/profile",
    response_model=schemas.UserProfileResponse,
    summary="사용자 프로필 조회",
)
async def get_user_profile(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> schemas.UserProfileResponse:
    """
    현재 사용자의 프로필 텍스트를 조회합니다.
    프로필 정보는 에이전트가 사용자에 대한 맥락을 파악하는 데 사용됩니다.

    Args:
        current_user: 인증된 사용자 정보.
        session: DB 작업을 위한 비동기 세션.

    Returns:
        schemas.UserProfileResponse: 사용자의 프로필 텍스트를 포함하는 응답.
    """
    logger.info(
        f"사용자 '{current_user.username}'의 프로필 조회를 요청했습니다."
    )
    profile_text = await chat_service.fetch_user_profile(
        db_session=session, user_id=current_user.user_id
    )
    logger.info(
        f"사용자 '{current_user.username}'의 프로필을 성공적으로 조회했습니다."
    )
    return schemas.UserProfileResponse(profile_text=profile_text)


@router.post(
    "/profile",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="사용자 프로필 업데이트",
)
async def update_user_profile(
    body: schemas.UserProfileUpdate,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> None:
    """
    현재 사용자의 프로필 정보를 생성하거나 업데이트합니다.

    Args:
        body (schemas.UserProfileUpdate): 업데이트할 프로필 텍스트를 포함하는 요청 본문.
        current_user: 인증된 사용자 정보.
        session: DB 작업을 위한 비동기 세션.
    """
    logger.info(
        f"사용자 '{current_user.username}'의 프로필 업데이트를 시작합니다."
    )
    await chat_service.upsert_user_profile(
        db_session=session,
        user_id=current_user.user_id,
        profile_text=body.profile_text,
    )
    logger.info(
        f"사용자 '{current_user.username}'의 프로필을 성공적으로 업데이트했습니다."
    )
    # HTTP 204 응답은 본문(body)을 포함하지 않으므로, 아무것도 반환하지 않습니다.
    return None
