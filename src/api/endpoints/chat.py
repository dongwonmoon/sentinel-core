"""
API 라우터: 채팅 (Chat)
- /chat/query: 에이전트에게 질문하고 스트리밍 응답 받기
- /chat/history: 이전 대화 기록 조회
- /chat/message: 대화 메시지 저장
"""

from fastapi import APIRouter, BackgroundTasks, Depends, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import dependencies, schemas
from ...core.agent import Agent
from ...core.logger import get_logger
from ...services import chat_service


router = APIRouter(prefix="/chat", tags=["Chat"])

logger = get_logger(__name__)


@router.post("/query")
async def query_agent(
    body: schemas.QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _: None = Depends(dependencies.enforce_chat_rate_limit),
    agent: Agent = Depends(dependencies.get_agent),
):
    """
    에이전트에게 질문하고, 답변을 스트리밍 방식으로 반환합니다.
    채팅 저장은 백그라운드에서 처리됩니다.
    """
    logger.info(
        f"사용자 '{current_user.username}'로부터 쿼리 수신: {body.query[:100]}..."
    )

    inputs = {
        "question": body.query,
        "permission_groups": current_user.permission_groups,
        "top_k": body.top_k,
        "doc_ids_filter": body.doc_ids_filter,
        "chat_history": (
            [msg.dict() for msg in body.chat_history] if body.chat_history else []
        ),
        "user_id": current_user.user_id,
        "session_id": body.session_id,
        "user_profile": current_user.profile_text or "",
    }
    logger.debug(f"사용자 '{current_user.username}'를 위한 에이전트 입력 준비 완료.")

    return StreamingResponse(
        chat_service.stream_agent_response(
            agent,
            inputs,
            background_tasks,
            session_id=body.session_id,
        ),
        media_type="text/event-stream",
    )


@router.post("/query-stream")
async def query_agent_stream(
    body: schemas.QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _: None = Depends(dependencies.enforce_chat_rate_limit),
    agent: Agent = Depends(dependencies.get_agent),
):
    """
    에이전트에게 질문하고, 답변을 스트리밍 방식으로 반환합니다. (POST 방식)
    채팅 저장은 백그라운드에서 처리됩니다.
    """
    logger.info(
        f"사용자 '{current_user.username}'로부터 스트림 쿼리 수신: {body.query[:100]}..."
    )

    inputs = {
        "question": body.query,
        "permission_groups": current_user.permission_groups,
        "top_k": body.top_k,
        "doc_ids_filter": body.doc_ids_filter,
        "chat_history": (
            [msg.dict() for msg in body.chat_history] if body.chat_history else []
        ),
        "user_id": current_user.user_id,
        "session_id": body.session_id,
        "user_profile": current_user.profile_text or "",
    }
    logger.debug(f"사용자 '{current_user.username}'를 위한 에이전트 입력 준비 완료.")

    return StreamingResponse(
        chat_service.stream_agent_response(
            agent,
            inputs,
            background_tasks,
            session_id=body.session_id,
        ),
        media_type="text/event-stream",
    )


@router.get("/sessions", response_model=schemas.ChatSessionListResponse)
async def get_chat_sessions(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """현재 사용자의 모든 채팅 세션 목록을 반환합니다."""
    logger.info(f"사용자 '{current_user.username}'의 세션 목록 조회.")
    sessions = await chat_service.fetch_user_sessions(
        session, current_user.user_id
    )
    logger.info(f"사용자 '{current_user.username}'의 세션 {len(sessions)}개 조회 완료.")
    return schemas.ChatSessionListResponse(sessions=sessions)


@router.get("/history/{session_id}", response_model=schemas.ChatHistoryResponse)
async def get_chat_history(
    session_id: str,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """특정 세션 ID에 대한 현재 사용자의 채팅 기록을 시간순으로 가져옵니다."""
    logger.info(f"사용자 '{current_user.username}'의 세션 '{session_id}' 기록 조회.")
    messages = await chat_service.fetch_chat_history(
        session, current_user.user_id, session_id
    )
    logger.info(
        f"사용자 '{current_user.username}'의 세션 '{session_id}' 메시지 {len(messages)}개 조회 완료."
    )
    return schemas.ChatHistoryResponse(messages=messages)


@router.get("/profile", response_model=dict)
async def get_user_profile(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    profile_text = await chat_service.fetch_user_profile(
        session, current_user.user_id
    )
    return {"profile_text": profile_text}


@router.post("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def update_user_profile(
    body: dict,  # e.g., {"profile_text": "I am a python developer"}
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    profile_text = body.get("profile_text", "")
    await chat_service.upsert_user_profile(
        session, current_user.user_id, profile_text
    )
    logger.info(f"사용자 '{current_user.username}' 프로필 업데이트 완료.")
