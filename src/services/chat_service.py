# -*- coding: utf-8 -*-
"""
채팅 및 에이전트와 관련된 핵심 비즈니스 로직을 담당하는 서비스 계층입니다.

이 파일은 API 엔드포인트와 데이터베이스 모델 사이의 중간 다리 역할을 하며,
복잡한 로직을 캡슐화하여 엔드포인트 코드를 간결하게 유지합니다.

주요 기능:
- 에이전트 응답 스트리밍 및 SSE(Server-Sent Events) 형식화
- 데이터베이스 CRUD(생성, 읽기, 업데이트, 삭제) 작업 수행
- 백그라운드 태스크를 이용한 후처리 작업 (대화 저장, 감사 로그 기록)
"""

from __future__ import annotations

import json
from typing import AsyncGenerator, Optional, Dict, Any

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..api import schemas
from ..core.agent import Agent
from ..core.logger import get_logger
from ..db import models

logger = get_logger(__name__)


async def stream_agent_response(
    agent: Agent,
    inputs: Dict[str, Any],
    background_tasks: BackgroundTasks,
    user_id: int,
    session_id: str,
) -> AsyncGenerator[str, None]:
    """
    에이전트의 응답을 스트리밍하고, 클라이언트에게 SSE(Server-Sent Events) 형식으로 전송합니다.

    이 함수는 LangGraph 에이전트의 실행 이벤트를 비동기적으로 순회하며,
    각 이벤트 유형에 따라 적절한 SSE 메시지를 생성하여 `yield`합니다.
    응답 스트림이 완료된 후에는, `background_tasks`를 사용하여 대화 기록 및
    감사 로그를 데이터베이스에 저장하는 후처리 작업을 예약합니다.

    Args:
        agent (Agent): 실행할 에이전트 인스턴스.
        inputs (dict): 에이전트 실행에 필요한 입력값.
        background_tasks (BackgroundTasks): 후처리 작업을 등록하기 위한 FastAPI의 백그라운드 태스크.
        user_id (int): 현재 사용자의 ID.
        session_id (str): 현재 채팅 세션의 ID.

    Yields:
        str: SSE 형식의 이벤트 문자열 (예: 'data: {"event": "token", "data": "hello"}\n\n').
    """
    final_answer = ""
    final_state: Optional[Dict[str, Any]] = None
    stream_started = False

    try:
        logger.info(
            f"세션 '{session_id}'에 대한 에이전트 스트리밍을 시작합니다."
        )
        # 에이전트의 `stream_response` 메서드를 호출하여 이벤트 스트림을 받습니다.
        async for event in agent.stream_response(inputs):
            kind = event.get("event")
            if not stream_started:
                logger.debug(
                    f"세션 '{session_id}'의 첫 이벤트를 수신했습니다: {kind}"
                )
                stream_started = True

            # 이벤트 종류가 'on_chat_model_stream' (LLM 토큰 생성)일 경우
            if kind == "on_chat_model_stream":
                # 이 이벤트가 'generate_final_answer' 노드에서 발생했는지 확인합니다.
                # 라우팅, 코드 생성 등 다른 노드의 LLM 호출은 최종 답변이 아니므로 무시합니다.
                node_name = event.get("metadata", {}).get("langgraph_node")
                if node_name != "generate_final_answer":
                    continue

                # 스트리밍된 토큰(content)을 `final_answer`에 누적하고,
                # 'token' 이벤트로 클라이언트에 즉시 전송합니다.
                content = event.get("data", {}).get("chunk", {}).content
                if content:
                    final_answer += content
                    yield _build_sse_payload("token", content)

            # 이벤트 종류가 'on_graph_end' (그래프 실행 종료)일 경우
            elif kind == "on_graph_end":
                logger.debug(
                    f"세션 '{session_id}'의 그래프 실행이 종료되었습니다."
                )
                final_state = event.get("data", {}).get("output")
                if final_state and isinstance(final_state, dict):
                    # RAG를 통해 검색된 소스(Source)가 있다면 'sources' 이벤트로 클라이언트에 전송합니다.
                    tool_outputs = final_state.get("tool_outputs", {})
                    rag_chunks = tool_outputs.get("rag_chunks", [])
                    sources = [schemas.Source(**chunk) for chunk in rag_chunks]
                    if sources:
                        sources_dict = [s.dict() for s in sources]
                        logger.info(
                            f"세션 '{session_id}'에 대해 {len(sources)}개의 소스를 찾았습니다."
                        )
                        yield _build_sse_payload("sources", sources_dict)

        # 모든 스트림이 성공적으로 끝나면 'end' 이벤트를 전송합니다.
        logger.info(
            f"세션 '{session_id}'의 스트리밍이 성공적으로 완료되었습니다."
        )
        yield _build_sse_payload("end", "Stream ended")

    except Exception as exc:
        logger.error(
            f"세션 '{session_id}' 스트리밍 중 예기치 않은 오류 발생: {exc}",
            exc_info=True,
        )
        # 클라이언트에 'error' 이벤트를 전송하여 오류 상황을 알립니다.
        yield _build_sse_payload(
            "error", f"스트리밍 중 서버에서 오류가 발생했습니다: {exc}"
        )

    finally:
        logger.debug(
            f"세션 '{session_id}'의 스트리밍 finally 블록 실행. 백그라운드 작업을 등록합니다."
        )
        # 스트림이 성공하든 실패하든 항상 실행되는 블록.
        # FastAPI의 BackgroundTasks를 사용하여 응답 전송을 막지 않는 후처리 작업을 등록합니다.
        background_tasks.add_task(
            save_chat_messages_task,
            agent=agent,
            user_id=user_id,
            session_id=session_id,
            user_query=inputs["question"],
            final_answer=final_answer,
        )
        if final_state:
            background_tasks.add_task(
                save_audit_log_task, state=final_state, agent=agent
            )


def _build_sse_payload(event: str, data: Any) -> str:
    """SSE(Server-Sent Events) 규격에 맞는 `data: {...}` 형식의 문자열을 생성합니다."""
    payload = json.dumps({"event": event, "data": data})
    return f"data: {payload}\n\n"


async def save_chat_messages_task(
    agent: Agent,
    user_id: int,
    session_id: str,
    user_query: str,
    final_answer: str,
):
    """
    [백그라운드 작업] 사용자 질문과 AI 답변을 DB에 비동기로 저장합니다.
    이 함수는 API 응답이 완료된 후에 실행되므로, 사용자 경험에 영향을 주지 않습니다.
    """
    logger.info(f"백그라운드 채팅 저장 작업 시작 (세션 ID: {session_id}).")
    # 에이전트가 가지고 있는 DB 세션 팩토리를 통해 새 세션을 생성합니다.
    # 의존성 주입으로 받은 세션을 사용하면, API 요청이 끝난 후 세션이 닫히므로
    # 백그라운드 작업에서는 새로운 세션을 만들어야 합니다.
    session_local = getattr(agent.vector_store, "AsyncSessionLocal", None)
    if not session_local:
        logger.error(
            "백그라운드 저장을 위한 DB 세션 팩토리를 찾을 수 없습니다."
        )
        return

    async with session_local() as session:
        try:
            # 사용자 메시지를 ChatHistory 모델 객체로 만들어 세션에 추가
            user_message = models.ChatHistory(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=user_query,
            )
            session.add(user_message)

            # AI 답변이 있을 경우, ChatHistory 모델 객체로 만들어 세션에 추가
            if final_answer:
                ai_message = models.ChatHistory(
                    user_id=user_id,
                    session_id=session_id,
                    role="assistant",
                    content=final_answer,
                )
                session.add(ai_message)

            # 세션에 추가된 모든 변경사항을 DB에 한 번에 커밋
            await session.commit()
            logger.info(
                f"사용자 '{user_id}'의 채팅 메시지를 세션 '{session_id}'에 성공적으로 저장했습니다."
            )
        except Exception as exc:
            logger.error(
                f"백그라운드 채팅 저장 중 오류 발생 (세션 ID: {session_id}): {exc}",
                exc_info=True,
            )
            await session.rollback()  # 오류 발생 시 롤백


async def save_audit_log_task(state: dict, agent: Agent):
    """
    [백그라운드 작업] 에이전트의 최종 상태 전체를 감사 로그 테이블에 기록합니다.
    이는 디버깅 및 에이전트 행동 분석에 매우 유용합니다.
    """
    session_id = state.get("session_id")
    logger.info(f"백그라운드 감사 로그 저장 작업 시작 (세션 ID: {session_id}).")
    session_local = getattr(agent.vector_store, "AsyncSessionLocal", None)
    if not session_local:
        logger.error("감사 로그 저장을 위한 DB 세션 팩토리를 찾을 수 없습니다.")
        return

    # AgentState 딕셔너리를 JSON으로 직렬화합니다. 순환 참조 등이 있을 수 있으므로 예외 처리.
    try:
        state_json = json.loads(json.dumps(state, default=str))
    except TypeError as exc:
        logger.error(
            f"AgentState 직렬화 실패 (세션 ID: {session_id}): {exc}. 일부만 저장합니다."
        )
        state_json = {
            "error": "state serialization failed",
            "original_exception": str(exc),
        }

    # AgentAuditLog 모델 객체를 생성합니다.
    log_entry = models.AgentAuditLog(
        session_id=session_id,
        question=state.get("question", "N/A"),
        permission_groups=state.get("permission_groups", []),
        tool_choice=state.get("tool_choice", "N/A"),
        code_input=state.get("code_input"),
        final_answer=state.get("answer", ""),
        full_agent_state=state_json,
    )

    async with session_local() as session:
        try:
            session.add(log_entry)
            await session.commit()
            logger.info(
                f"감사 로그를 성공적으로 저장했습니다 (세션 ID: {session_id})."
            )
        except Exception as exc:
            logger.error(
                f"감사 로그 저장 중 오류 발생 (세션 ID: {session_id}): {exc}",
                exc_info=True,
            )
            await session.rollback()


async def fetch_user_sessions(
    db_session: AsyncSession, user_id: int
) -> list[schemas.ChatSession]:
    """
    특정 사용자의 모든 채팅 세션 목록을 최신순으로 조회합니다.

    이 쿼리는 두 개의 CTE(Common Table Expression)를 사용하여 효율적으로 작동합니다.
    1. `ranked_messages_cte`: 각 세션 내에서 'user' 역할의 메시지들에 시간순으로 순위를 매깁니다.
    2. `latest_activity_cte`: 각 세션의 마지막 활동(메시지) 시간을 찾습니다.

    최종적으로 두 CTE를 조인하여, 각 세션의 첫 번째 사용자 메시지를 제목으로,
    그리고 마지막 활동 시간을 기준으로 정렬된 세션 목록을 만듭니다.

    Args:
        db_session (AsyncSession): 데이터베이스 작업을 위한 세션.
        user_id (int): 세션 목록을 조회할 사용자의 ID.

    Returns:
        list[schemas.ChatSession]: Pydantic 스키마로 변환된 채팅 세션 목록.
    """
    logger.debug(
        f"사용자 '{user_id}'의 채팅 세션 목록 조회를 위한 쿼리를 구성합니다."
    )
    # CTE 1: ranked_messages
    ranked_messages_cte = (
        select(
            models.ChatHistory.session_id,
            models.ChatHistory.content,
            models.ChatHistory.created_at,
            func.row_number()
            .over(
                partition_by=models.ChatHistory.session_id,
                order_by=models.ChatHistory.created_at.asc(),
            )
            .label("rn"),
        )
        .where(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.role == "user",
            models.ChatHistory.session_id.isnot(None),
        )
        .cte("ranked_messages")
    )

    # CTE 2: latest_activity
    latest_activity_cte = (
        select(
            models.ChatHistory.session_id,
            func.max(models.ChatHistory.created_at).label("last_updated"),
        )
        .where(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.session_id.isnot(None),
        )
        .group_by(models.ChatHistory.session_id)
        .cte("latest_activity")
    )

    # 최종 쿼리
    stmt = (
        select(
            ranked_messages_cte.c.session_id,
            func.left(ranked_messages_cte.c.content, 50).label("title"),
            latest_activity_cte.c.last_updated,
        )
        .join(
            latest_activity_cte,
            ranked_messages_cte.c.session_id
            == latest_activity_cte.c.session_id,
        )
        .where(ranked_messages_cte.c.rn == 1)
        .order_by(latest_activity_cte.c.last_updated.desc())
    )

    result = await db_session.execute(stmt)
    sessions = [schemas.ChatSession(**row._asdict()) for row in result]
    logger.debug(
        f"사용자 '{user_id}'에 대해 {len(sessions)}개의 세션을 조회했습니다."
    )
    return sessions


async def fetch_chat_history(
    db_session: AsyncSession, user_id: int, session_id: str
) -> list[schemas.ChatMessageInDB]:
    """특정 세션의 전체 대화 기록을 시간순으로 조회합니다."""
    logger.debug(
        f"사용자 '{user_id}'의 세션 '{session_id}' 대화 기록 조회를 시작합니다."
    )
    stmt = (
        select(models.ChatHistory)
        .where(
            models.ChatHistory.user_id == user_id,
            models.ChatHistory.session_id == session_id,
        )
        .order_by(models.ChatHistory.created_at.asc())
    )
    result = await db_session.execute(stmt)
    messages = [
        schemas.ChatMessageInDB.from_orm(row) for row in result.scalars()
    ]
    logger.debug(
        f"세션 '{session_id}'에서 {len(messages)}개의 메시지를 조회했습니다."
    )
    return messages


async def fetch_user_profile(db_session: AsyncSession, user_id: int) -> str:
    """사용자 프로필 텍스트를 조회합니다."""
    logger.debug(f"사용자 '{user_id}'의 프로필 조회를 시작합니다.")
    stmt = select(models.UserProfile.profile_text).where(
        models.UserProfile.user_id == user_id
    )
    profile = await db_session.scalar(stmt)
    logger.debug(f"사용자 '{user_id}'의 프로필 조회 완료.")
    return profile or ""


async def upsert_user_profile(
    db_session: AsyncSession, user_id: int, profile_text: str
) -> None:
    """
    사용자 프로필을 생성하거나 업데이트합니다 (Upsert).

    PostgreSQL의 `ON CONFLICT DO UPDATE` 기능을 사용하여 원자적(atomic)으로
    데이터를 처리합니다. 이를 통해 프로필이 없을 때는 새로 생성하고,
    이미 존재할 때는 내용을 업데이트하는 동작을 단일 쿼리로 안전하게 수행합니다.

    Args:
        db_session (AsyncSession): 데이터베이스 작업을 위한 세션.
        user_id (int): 프로필을 업데이트할 사용자의 ID.
        profile_text (str): 저장할 프로필 내용.
    """
    logger.debug(f"사용자 '{user_id}'의 프로필 upsert를 시작합니다.")
    stmt = pg_insert(models.UserProfile).values(
        user_id=user_id, profile_text=profile_text.strip()
    )
    update_stmt = stmt.on_conflict_do_update(
        index_elements=[models.UserProfile.user_id],
        set_={"profile_text": stmt.excluded.profile_text},
    )
    await db_session.execute(update_stmt)
    logger.info(f"사용자 '{user_id}'의 프로필을 성공적으로 upsert했습니다.")
