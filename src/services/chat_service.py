"""채팅/에이전트 관련 비즈니스 로직을 담당하는 서비스 계층."""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional

from fastapi import BackgroundTasks
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..api import schemas
from ..core.agent import Agent
from ..core.logger import get_logger

logger = get_logger(__name__)


async def stream_agent_response(
    agent: Agent,
    inputs: dict,
    background_tasks: BackgroundTasks,
    session_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """LangGraph 이벤트를 SSE 응답 형식으로 변환하고, 후처리를 백그라운드로 위임."""
    final_answer = ""
    final_state: Optional[dict] = None

    try:
        async for event in agent.stream_response(inputs):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                node_name = event.get("metadata", {}).get("langgraph_node") or event.get(
                    "metadata", {}
                ).get("run_name")
                if node_name != "generate_final_answer":
                    continue
                content = event["data"]["chunk"].content
                if content:
                    final_answer += content
                    yield _build_sse_payload("token", content)

            elif kind == "on_graph_end":
                final_state = event["data"]["output"]
                if final_state and isinstance(final_state, dict):
                    tool_outputs = final_state.get("tool_outputs", {})
                    rag_chunks = tool_outputs.get("rag_chunks", [])
                    sources = [schemas.Source(**chunk) for chunk in rag_chunks]
                    if sources:
                        sources_dict = [s.dict() for s in sources]
                        yield _build_sse_payload("sources", sources_dict)

        yield _build_sse_payload("end", None)

    except Exception as exc:  # pragma: no cover - 방어적 로깅
        logger.error(f"스트리밍 중 오류: {exc}", exc_info=True)
        yield _build_sse_payload("error", str(exc))

    finally:
        background_tasks.add_task(
            save_chat_messages_task,
            agent=agent,
            user_id=inputs["user_id"],
            session_id=session_id,
            user_query=inputs["question"],
            final_answer=final_answer,
        )
        if final_state:
            background_tasks.add_task(save_audit_log_task, state=final_state, agent=agent)


def _build_sse_payload(event: str, data) -> str:
    """SSE 규격 문자열을 생성."""
    return f"data: {json.dumps({'event': event, 'data': data})}\n\n"


async def save_chat_messages_task(
    agent: Agent,
    user_id: int,
    session_id: Optional[str],
    user_query: str,
    final_answer: str,
):
    """스트림 종료 후 사용자/AI 메시지를 비동기로 저장."""
    logger.debug(f"백그라운드 채팅 저장 작업 시작 (세션 ID: {session_id}).")
    session_local = getattr(agent.vector_store, "AsyncSessionLocal", None)
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
        except Exception as exc:
            logger.error(f"백그라운드 채팅 저장 중 오류: {exc}", exc_info=True)
            await session.rollback()
    logger.debug(f"백그라운드 저장 작업 종료 (세션 ID: {session_id}).")


async def save_audit_log_task(state: dict, agent: Agent):
    """에이전트 상태 전체를 감사 로그 테이블에 기록."""
    logger.debug("백그라운드 감사 로그 저장 작업 시작.")
    session_local = getattr(agent.vector_store, "AsyncSessionLocal", None)
    if not session_local:
        logger.error("감사 로그 저장을 위한 DB 세션 팩토리 없음.")
        return

    try:
        state_json_str = json.dumps(state, default=str)
    except TypeError as exc:
        logger.error(f"AgentState 직렬화 실패: {exc}. 일부만 저장합니다.")
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
        except Exception as exc:
            logger.error(f"감사 로그 저장 중 오류: {exc}", exc_info=True)
            await session.rollback()
    logger.debug("백그라운드 감사 로그 저장 작업 종료.")


async def _save_chat_message(
    message: schemas.ChatMessageBase,
    session: AsyncSession,
    user_id: int,
    session_id: Optional[str] = None,
):
    """단일 채팅 메시지를 chat_history 테이블에 INSERT."""
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
    except Exception as exc:  # pragma: no cover - 실패 시 로깅만
        logger.error(
            f"사용자 ID '{user_id}', 역할 '{message.role}'의 채팅 메시지 저장 중 오류 발생: {exc}",
            exc_info=True,
        )


async def fetch_user_sessions(
    session: AsyncSession, user_id: int
) -> list[schemas.ChatSession]:
    """사용자별 세션 목록을 최신순으로 반환."""
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
            LEFT(r.content, 50) as title,
            l.last_updated
        FROM ranked_messages r
        JOIN latest_activity l ON r.session_id = l.session_id
        WHERE r.rn = 1
        ORDER BY l.last_updated DESC
        """
    )
    result = await session.execute(stmt, {"user_id": user_id})
    return [schemas.ChatSession(**row._asdict()) for row in result]


async def fetch_chat_history(
    session: AsyncSession, user_id: int, session_id: str
) -> list[schemas.ChatMessageInDB]:
    """특정 세션의 히스토리를 시간순으로 반환."""
    stmt = text(
        """
        SELECT role, content, created_at 
        FROM chat_history
        WHERE user_id = :user_id 
          AND session_id = :session_id
        ORDER BY created_at ASC
        """
    )
    result = await session.execute(
        stmt, {"user_id": user_id, "session_id": session_id}
    )
    return [schemas.ChatMessageInDB(**row._asdict()) for row in result]


async def fetch_user_profile(session: AsyncSession, user_id: int) -> str:
    """사용자 프로필 텍스트를 반환."""
    stmt = text("SELECT profile_text FROM user_profile WHERE user_id = :user_id")
    result = await session.execute(stmt, {"user_id": user_id})
    profile = result.fetchone()
    return profile.profile_text if profile else ""


async def upsert_user_profile(
    session: AsyncSession, user_id: int, profile_text: str
) -> None:
    """사용자 프로필을 생성/갱신."""
    stmt = text(
        """
        INSERT INTO user_profile (user_id, profile_text)
        VALUES (:user_id, :profile_text)
        ON CONFLICT (user_id) DO UPDATE SET profile_text = EXCLUDED.profile_text
        """
    )
    await session.execute(
        stmt, {"user_id": user_id, "profile_text": profile_text.strip()}
    )
