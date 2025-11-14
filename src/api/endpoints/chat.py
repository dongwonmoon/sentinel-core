"""
API 라우터: 채팅 (Chat)
- /chat/query: 에이전트에게 질문하고 스트리밍 응답 받기
- /chat/history: 이전 대화 기록 조회
- /chat/message: 대화 메시지 저장
"""

import json
from typing import AsyncGenerator, Optional, List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .. import dependencies, schemas
from ...core.agent import Agent
from ...core.logger import get_logger


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)

logger = get_logger(__name__)


async def save_chat_messages_task(
    agent: Agent,
    user_id: int,
    session_id: Optional[str],
    user_query: str,
    final_answer: str,
):
    """스트림이 끝난 후, 사용자/AI 메시지를 DB에 저장합니다."""
    logger.debug(f"백그라운드 채팅 저장 작업 시작 (세션 ID: {session_id}).")
    session_local = agent.vector_store.AsyncSessionLocal
    if not session_local:
        logger.error("백그라운드 저장을 위한 DB 세션 팩토리 없음.")
        return

    async with session_local() as session:
        try:
            user_message = schemas.ChatMessageBase(role="user", content=user_query)
            await _save_chat_message(
                user_message,
                session=session,
                user_id=user_id,
                session_id=session_id,
            )
            if final_answer:
                ai_message = schemas.ChatMessageBase(
                    role="assistant", content=final_answer
                )
                await _save_chat_message(
                    ai_message,
                    session=session,
                    user_id=user_id,
                    session_id=session_id,
                )
            await session.commit()
            logger.info(f"백그라운드 채팅 저장 완료 (세션 ID: {session_id}).")
        except Exception as e:
            logger.error(f"백그라운드 채팅 저장 중 오류: {e}", exc_info=True)
            await session.rollback()
    logger.debug(f"백그라운드 저장 작업 종료 (세션 ID: {session_id}).")


async def save_audit_log_task(state: dict, agent: Agent):
    """스트림이 끝난 후, 에이전트 감사 로그를 DB에 저장합니다."""
    logger.debug("백그라운드 감사 로그 저장 작업 시작.")
    session_local = agent.vector_store.AsyncSessionLocal
    if not session_local:
        logger.error("감사 로그 저장을 위한 DB 세션 팩토리 없음.")
        return

    try:
        state_json_str = json.dumps(state, default=str)
    except TypeError as e:
        logger.error(f"AgentState 직렬화 실패: {e}. 일부만 저장합니다.")
        state_json_str = json.dumps({"error": "state serialization failed"})

    log_data = {
        "session_id": state.get("session_id"),
        "question": state.get("question", "N/A"),
        "permission_groups": state.get("permission_groups", []),
        "tool_choice": state.get("tool_choice", "N/A"),
        "code_input": state.get("code_input"),
        "final_answer": state.get("answer", ""),
        "full_agent_state": state_json_str,
    }

    async with session_local() as session:
        try:
            async with session.begin():
                stmt = text(
                    """
                    INSERT INTO agent_audit_log 
                    (session_id, question, permission_groups, tool_choice, code_input, final_answer, full_agent_state)
                    VALUES (:session_id, :question, :permission_groups, :tool_choice, :code_input, :final_answer, :full_agent_state::jsonb)
                    """
                )
                await session.execute(stmt, log_data)
            logger.info(f"감사 로그 저장 완료 (Q: {log_data['question'][:20]}...)")
        except Exception as e:
            logger.error(f"감사 로그 저장 중 오류: {e}", exc_info=True)
            await session.rollback()
    logger.debug("백그라운드 감사 로그 저장 작업 종료.")


async def _stream_agent_response(
    agent: Agent,
    inputs: dict,
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """
    에이전트 응답을 스트리밍하고, 완료 후 DB 저장을 백그라운드 태스크에 위임합니다.
    """
    final_answer = ""
    final_state = None
    sources = []

    try:
        async for event in agent.stream_response(inputs):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                node_name = event.get("metadata", {}).get(
                    "langgraph_node"
                ) or event.get("metadata", {}).get("run_name")
                if node_name != "generate_final_answer":
                    continue
                content = event["data"]["chunk"].content
                if content:
                    final_answer += content
                    yield f"data: {json.dumps({'event': 'token', 'data': content})}\n\n"

            elif kind == "on_graph_end":
                final_state = event["data"]["output"]
                if final_state and isinstance(final_state, dict):
                    tool_outputs = final_state.get("tool_outputs", {})
                    rag_chunks = tool_outputs.get("rag_chunks", [])
                    sources = [schemas.Source(**chunk) for chunk in rag_chunks]
                    if sources:
                        sources_dict = [s.dict() for s in sources]
                        yield f"data: {json.dumps({'event': 'sources', 'data': sources_dict})}\n\n"

        yield f"data: {json.dumps({'event': 'end'})}\n\n"

    except Exception as e:
        logger.error(f"스트리밍 중 오류: {e}", exc_info=True)
        yield f"data: {json.dumps({'event': 'error', 'data': str(e)})}\n\n"

    finally:
        background_tasks.add_task(
            save_chat_messages_task,
            agent=agent,
            user_id=inputs["user_id"],
            session_id=session_id,
            user_query=inputs["question"],
            final_answer=final_answer,
        )
        logger.debug(
            f"채팅 메시지 저장 작업이 백그라운드 태스크에 추가됨 (세션 ID: {session_id})."
        )
        if final_state:
            background_tasks.add_task(
                save_audit_log_task, state=final_state, agent=agent
            )
            logger.debug("감사 로그 저장 작업이 백그라운드 태스크에 추가됨.")


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
        _stream_agent_response(
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
        _stream_agent_response(
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
    from sqlalchemy import text

    logger.info(f"사용자 '{current_user.username}'의 세션 목록 조회.")

    # 복잡하지만 효율적인 SQL 쿼리:
    # 1. (ranked_messages) 각 세션(session_id)별로 가장 먼저 작성된(rn = 1) 'user' 메시지를 찾습니다.
    # 2. (latest_activity) 각 세션별로 가장 최근 메시지 시간(last_updated)을 찾습니다.
    # 3. 이 두 결과를 조인하여 세션 ID, 제목(첫 메시지 50자), 최종 업데이트 시간을 가져옵니다.
    stmt = text(
        """
        WITH ranked_messages AS (
            SELECT 
                session_id,
                content,
                created_at,
                ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY created_at ASC) as rn
            FROM chat_history
            WHERE user_id = :user_id 
              AND role = 'user' 
              AND session_id IS NOT NULL
        ),
        latest_activity AS (
            SELECT 
                session_id,
                MAX(created_at) as last_updated
            FROM chat_history
            WHERE user_id = :user_id AND session_id IS NOT NULL
            GROUP BY session_id
        )
        SELECT 
            r.session_id,
            LEFT(r.content, 50) as title, -- 제목으로 50자만 사용
            l.last_updated
        FROM ranked_messages r
        JOIN latest_activity l ON r.session_id = l.session_id
        WHERE r.rn = 1
        ORDER BY l.last_updated DESC -- 최근 대화 순으로 정렬
        """
    )
    result = await session.execute(stmt, {"user_id": current_user.user_id})

    # SQLAlchemy Row 객체를 Pydantic 모델로 변환
    sessions = [schemas.ChatSession(**row._asdict()) for row in result]

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
    from sqlalchemy import text

    stmt = text(
        """
        SELECT role, content, created_at 
        FROM chat_history
        WHERE user_id = :user_id 
          AND session_id = :session_id -- 3. session_id로 필터링하는 조건 추가
        ORDER BY created_at ASC
        """
    )
    result = await session.execute(
        stmt, {"user_id": current_user.user_id, "session_id": session_id}
    )
    messages = [schemas.ChatMessageInDB(**row._asdict()) for row in result]
    logger.info(
        f"사용자 '{current_user.username}'의 세션 '{session_id}' 메시지 {len(messages)}개 조회 완료."
    )
    return schemas.ChatHistoryResponse(messages=messages)


async def _save_chat_message(
    message: schemas.ChatMessageBase,
    session: AsyncSession,
    user_id: int,
    session_id: Optional[str] = None,
):
    """'user' 또는 'assistant'의 단일 메시지를 DB에 저장하는 헬퍼 함수."""
    from sqlalchemy import text

    try:
        logger.debug(
            f"사용자 ID '{user_id}', 역할 '{message.role}'의 채팅 메시지 저장 시도."
        )
        stmt = text(
            """
            INSERT INTO chat_history (user_id, role, content, session_id)
            VALUES (:user_id, :role, :content, :session_id)
            """
        )
        await session.execute(
            stmt,
            {
                "user_id": user_id,
                "role": message.role,
                "content": message.content,
                "session_id": session_id,
            },
        )
        logger.debug(f"사용자 ID '{user_id}'의 채팅 메시지 저장 성공.")
    except Exception as e:
        # 이 함수는 스트림의 일부로 호출되므로, 실패 시 HTTP 예외를 발생시키지 않고 로깅만 합니다.
        logger.error(
            f"사용자 ID '{user_id}', 역할 '{message.role}'의 채팅 메시지 저장 중 오류 발생: {e}",
            exc_info=True,
        )
        print(f"채팅 메시지 저장 중 오류 발생: {e}")


@router.get("/profile", response_model=dict)
async def get_user_profile(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    stmt = text("SELECT profile_text FROM user_profile WHERE user_id = :user_id")
    result = await session.execute(stmt, {"user_id": current_user.user_id})
    profile = result.fetchone()
    return {"profile_text": profile.profile_text if profile else ""}


@router.post("/profile", status_code=status.HTTP_204_NO_CONTENT)
async def update_user_profile(
    body: dict,  # e.g., {"profile_text": "I am a python developer"}
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    profile_text = body.get("profile_text", "")
    stmt = text(
        """
        INSERT INTO user_profile (user_id, profile_text)
        VALUES (:user_id, :profile_text)
        ON CONFLICT (user_id) DO UPDATE SET profile_text = EXCLUDED.profile_text
        """
    )
    await session.execute(
        stmt, {"user_id": current_user.user_id, "profile_text": profile_text}
    )
    logger.info(f"사용자 '{current_user.username}' 프로필 업데이트 완료.")
