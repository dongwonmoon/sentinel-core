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
import redis.asyncio as aioredis

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..api import schemas
from ..core.agent import Agent
from ..core.logger import get_logger
from ..db import models

logger = get_logger(__name__)

# SSE 이벤트에서 'tool'로 간주할 노드 이름 목록
TOOL_NODES = [
    "run_rag_tool",
    "run_web_search_tool",
    "run_code_execution_tool",
    "run_dynamic_tool",
]


async def build_stateful_agent_inputs(
    redis: aioredis.Redis,
    db_session: AsyncSession,
    user_id: int,
    session_id: str,
    query: str,
    top_k: int,
    user_profile: str,
) -> Dict[str, Any]:
    """
    에이전트(LangGraph) 실행에 필요한 모든 입력(AgentState)을 구성합니다.
    서버 측(Redis)에 저장된 세션 컨텍스트를 로드하고, DB에서 대화 기록을 가져와
    하나의 딕셔너리로 조합하여 반환합니다.

    Args:
        redis: Redis 클라이언트 인스턴스.
        db_session: 데이터베이스 세션.
        user_id: 현재 사용자 ID.
        session_id: 현재 채팅 세션 ID.
        query: 사용자의 현재 질문.
        top_k: RAG에서 사용할 상위 K개 문서 수.
        user_profile: 사용자의 프로필 정보.

    Returns:
        Dict[str, Any]: AgentState를 구성하는 데 사용될 완전한 입력 딕셔너리.
    """
    session_key = f"session_context:{session_id}"

    # Redis에서 현재 세션의 컨텍스트(예: RAG 문서 필터)를 로드합니다.
    doc_ids_filter = None
    try:
        context_raw = await redis.get(session_key)
        if context_raw:
            context = json.loads(context_raw)
            doc_ids_filter = context.get("doc_ids_filter")
            logger.debug(f"세션 '{session_id}'의 컨텍스트를 Redis에서 로드했습니다.")
    except Exception as e:
        # Redis는 세션 컨텍스트와 같은 비영구적 데이터를 저장하는 데 사용됩니다.
        # 만약 Redis에 장애가 발생하더라도, 채팅의 핵심 기능(LLM 호출, DB 기록)은
        # 계속 작동해야 합니다. 따라서 오류를 로깅만 하고 무시하여 서비스의
        # 가용성을 높입니다. 이 경우 RAG 필터링 등 일부 기능이 동작하지 않을 수 있습니다.
        logger.warning(f"세션 '{session_id}'의 Redis 컨텍스트 로드 실패: {e}")

    # DB에서 이전 대화 기록을 로드합니다.
    chat_history_models = await fetch_chat_history(
        db_session=db_session, user_id=user_id, session_id=session_id
    )
    chat_history = [
        {"role": msg.role, "content": msg.content} for msg in chat_history_models
    ]

    # 모든 정보를 종합하여 AgentState의 입력으로 사용될 딕셔너리를 구성합니다.
    inputs = {
        "question": query,
        "top_k": top_k,
        "user_profile": user_profile,
        "chat_history": chat_history,
        "doc_ids_filter": doc_ids_filter,
        "session_id": str(session_id),
        "user_id": str(user_id),
    }

    return inputs


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

    # 도구 사용 후 생성되는 첫 번째 토큰에 'new_message: true' 플래그를 붙여주기 위한 상태 값.
    # 프론트엔드는 이 플래그를 보고, 도구 사용 결과를 별도의 메시지 블록으로 렌더링할 수 있습니다.
    force_new_message_after_tool = False

    try:
        logger.info(f"세션 '{session_id}'에 대한 에이전트 스트리밍을 시작합니다.")
        # 에이전트의 `stream_response` 메서드를 호출하여 이벤트 스트림을 받습니다.
        async for event in agent.stream_response(inputs):
            kind = event.get("event")
            if not stream_started:
                logger.debug(f"세션 '{session_id}'의 첫 이벤트를 수신했습니다: {kind}")
                stream_started = True

            # 'on_node_start': 특정 노드(도구) 실행 시작을 클라이언트에 알립니다.
            # UI는 이 이벤트를 받아 해당 도구에 대한 로딩 인디케이터를 표시할 수 있습니다.
            if kind == "on_node_start":
                node_name = event.get("name")
                if node_name in TOOL_NODES:
                    logger.debug(f"Tool Node Start: {node_name}")
                    yield _build_sse_payload("tool_start", {"name": node_name})
                    # 도구가 실행되었으므로, 다음에 오는 LLM 응답은 새 메시지로 처리해야 함을 표시합니다.
                    force_new_message_after_tool = True

            # 'on_node_end': 노드 실행이 끝났음을 클라이언트에 알립니다.
            # UI는 로딩 인디케이터를 숨깁니다.
            elif kind == "on_node_end":
                node_name = event.get("name")
                if node_name in TOOL_NODES:
                    logger.debug(f"Tool Node End: {node_name}")
                    yield _build_sse_payload("tool_end", {"name": node_name})

            # 'on_chat_model_stream': LLM이 스트리밍으로 토큰을 생성할 때 발생합니다.
            elif kind == "on_chat_model_stream":
                # 이 이벤트가 최종 답변을 생성하는 'generate_final_answer' 노드에서 발생했는지 확인합니다.
                # 라우팅, 코드 생성 등 중간 단계의 LLM 호출 결과는 최종 사용자에게 보여주지 않기 위함입니다.
                node_name = event.get("metadata", {}).get("langgraph_node")
                if node_name != "generate_final_answer":
                    continue

                content = event.get("data", {}).get("chunk", {}).content
                if content:
                    final_answer += content
                    new_message_flag = False
                    if force_new_message_after_tool:
                        # 도구 실행 직후의 첫 토큰인 경우, 'new_message' 플래그를 True로 설정합니다.
                        # 프론트엔드는 이를 보고 기존 메시지에 이어붙이지 않고 새 메시지 블록을 생성합니다.
                        new_message_flag = True
                        force_new_message_after_tool = (
                            False  # 플래그는 한 번만 사용 후 초기화
                        )

                    yield _build_sse_payload(
                        "token",
                        {"chunk": content, "new_message": new_message_flag},
                    )

            # 'on_graph_end': 에이전트(그래프)의 모든 실행이 완료되었을 때 발생합니다.
            elif kind == "on_graph_end":
                logger.debug(f"세션 '{session_id}'의 그래프 실행이 종료되었습니다.")
                final_state = event.get("data", {}).get("output")
                if final_state and isinstance(final_state, dict):
                    # RAG를 통해 검색된 소스(Source)가 있다면 'sources' 이벤트로 클라이언트에 전송합니다.
                    # 이는 답변의 근거를 사용자에게 투명하게 보여주기 위함입니다.
                    tool_outputs = final_state.get("tool_outputs", {})
                    rag_chunks = tool_outputs.get("rag_chunks", [])
                    sources = [schemas.Source(**chunk) for chunk in rag_chunks]
                    if sources:
                        sources_dict = [s.dict() for s in sources]
                        logger.info(
                            f"세션 '{session_id}'에 대해 {len(sources)}개의 소스를 찾았습니다."
                        )
                        yield _build_sse_payload("sources", sources_dict)

        # 모든 스트림이 성공적으로 끝나면 'end' 이벤트를 전송하여 클라이언트가 연결 종료를 준비하게 합니다.
        logger.info(f"세션 '{session_id}'의 스트리밍이 성공적으로 완료되었습니다.")
        yield _build_sse_payload("end", "Stream ended")

    except Exception as exc:
        logger.error(
            f"세션 '{session_id}' 스트리밍 중 예기치 않은 오류 발생: {exc}",
            exc_info=True,
        )
        # 클라이언트에 'error' 이벤트를 전송하여 오류 상황을 명확히 알리고,
        # 프론트엔드에서 적절한 오류 메시지를 표시할 수 있도록 합니다.
        yield _build_sse_payload(
            "error", f"스트리밍 중 서버에서 오류가 발생했습니다: {exc}"
        )

    finally:
        # 스트림이 성공하든 실패하든 항상 실행되는 블록입니다.
        # FastAPI의 BackgroundTasks를 사용하여 응답 전송을 막지 않는 후처리 작업을 등록합니다.
        # 이를 통해 DB 저장과 같은 I/O 바운드 작업이 사용자 응답 시간에 영향을 주지 않도록 합니다.
        logger.debug(
            f"세션 '{session_id}'의 스트리밍 finally 블록 실행. 백그라운드 작업을 등록합니다."
        )
        background_tasks.add_task(
            save_chat_messages_task,
            agent=agent,
            user_id=user_id,
            session_id=session_id,
            user_query=inputs["question"],
            final_answer=final_answer,
        )


def _build_sse_payload(event: str, data: Any) -> str:
    """SSE(Server-Sent Events) 규격에 맞는 `data: {...}` 형식의 문자열을 생성합니다."""
    # 클라이언트(브라우저)와 약속된 JSON 구조로 데이터를 감쌉니다.
    payload = json.dumps({"event": event, "data": data})
    # SSE 형식은 "data: "로 시작하고 "\n\n"으로 끝나야 합니다.
    return f"data: {payload}\n\n"


async def create_session_attachment(
    db_session: AsyncSession,
    session_id: str,
    user_id: int,
    file_name: str,
    file_path: str,  # Git URL, S3 Key, local path 등
    status: str = "indexing",
) -> models.SessionAttachment:
    """
    (신규) SessionAttachment DB 레코드를 생성하고 반환합니다.
    """
    try:
        new_attachment = models.SessionAttachment(
            session_id=session_id,
            user_id=user_id,
            file_name=file_name,
            file_path=file_path,
            status=status,
        )
        db_session.add(new_attachment)
        await db_session.commit()
        # commit 후, DB에 의해 자동 생성된 ID와 같은 최신 상태를 객체에 반영합니다.
        await db_session.refresh(new_attachment)
        logger.debug(
            f"DB 레코드 생성 완료 (Attachment ID: {new_attachment.attachment_id})"
        )
        return new_attachment
    except Exception as e:
        # DB 작업 중 오류가 발생하면, 트랜잭션을 롤백하여 데이터 일관성을 유지합니다.
        await db_session.rollback()
        logger.error(f"첨부파일 DB 레코드 생성 실패: {e}", exc_info=True)
        # 클라이언트에게 서버 내부 오류가 발생했음을 알립니다.
        raise HTTPException(status_code=500, detail="DB record creation failed.")


async def save_chat_messages_task(
    agent: Agent,
    user_id: int,
    session_id: str,
    user_query: str,
    final_answer: str,
):
    """
    [백그라운드 작업] 사용자 질문과 AI 답변을 DB에 비동기로 저장합니다.
    이 함수는 API 응답이 완료된 후 실행되므로 사용자 경험에 영향을 주지 않습니다.
    """
    logger.info(f"백그라운드 채팅 저장 작업 시작 (세션 ID: {session_id}).")
    # 백그라운드 태스크는 원래 요청의 DB 세션과 분리되어 있으므로,
    # 새로운 DB 세션을 생성해야 합니다. 벡터 저장소에서 세션 팩토리를 가져옵니다.
    session_local = getattr(agent.vector_store, "AsyncSessionLocal", None)
    if not session_local:
        logger.error("백그라운드 저장을 위한 DB 세션 팩토리를 찾을 수 없습니다.")
        return

    # 'async with'를 사용하여 세션이 끝나면 자동으로 닫히도록 합니다.
    async with session_local() as session:
        try:
            # 사용자 질문과 AI 답변을 한 쌍으로 저장하여 대화의 맥락을 유지합니다.
            # 이 기록은 다음 턴에 'chat_history'로 에이전트에게 전달됩니다.
            user_message = models.ChatHistory(
                user_id=user_id,
                session_id=session_id,
                role="user",
                content=user_query,
            )
            session.add(user_message)

            # AI 답변이 있는 경우에만 (예: 스트림 오류가 없었던 경우) 저장합니다.
            if final_answer:
                ai_message = models.ChatHistory(
                    user_id=user_id,
                    session_id=session_id,
                    role="assistant",
                    content=final_answer,
                )
                session.add(ai_message)

            # session.add()로 추가된 모든 변경사항(user_message, ai_message)을
            # 하나의 트랜잭션으로 DB에 커밋합니다.
            await session.commit()
            logger.info(
                f"사용자 '{user_id}'의 채팅 메시지를 세션 '{session_id}'에 성공적으로 저장했습니다."
            )
        except Exception as exc:
            # DB 저장 중 오류 발생 시, 롤백하여 부분 저장을 방지하고 데이터 일관성을 지킵니다.
            logger.error(
                f"백그라운드 채팅 저장 중 오류 발생 (세션 ID: {session_id}): {exc}",
                exc_info=True,
            )
            await session.rollback()


async def fetch_session_attachments(
    db_session: AsyncSession, user_id: int, session_id: str
) -> list[schemas.SessionAttachmentResponse]:
    """특정 세션에 첨부된 파일 목록을 상태와 함께 반환합니다."""
    stmt = (
        select(models.SessionAttachment)
        .where(
            models.SessionAttachment.user_id == user_id,
            models.SessionAttachment.session_id == session_id,
        )
        .order_by(models.SessionAttachment.created_at.desc())
    )
    result = await db_session.execute(stmt)
    attachments = result.scalars().all()
    return [
        schemas.SessionAttachmentResponse.model_validate(att) for att in attachments
    ]


async def fetch_user_sessions(
    db_session: AsyncSession, user_id: int
) -> list[schemas.ChatSession]:
    """
    특정 사용자의 모든 채팅 세션 목록을 최신순으로 조회합니다.

    이 쿼리는 두 개의 CTE(Common Table Expression)를 사용하여 효율적으로 작동합니다.
    1. `ranked_messages_cte`: 각 세션 내에서 'user' 역할의 메시지들에 시간순으로 순위를 매깁니다.
       이를 통해 각 세션의 '첫 번째' 사용자 메시지를 식별할 수 있습니다.
    2. `latest_activity_cte`: 각 세션의 마지막 활동(메시지) 시간을 찾습니다.

    최종적으로 두 CTE를 조인하여, 각 세션의 첫 번째 사용자 메시지를 제목(title)으로,
    그리고 마지막 활동 시간을 기준으로 정렬된 세션 목록을 만듭니다.

    Args:
        db_session (AsyncSession): 데이터베이스 작업을 위한 세션.
        user_id (int): 세션 목록을 조회할 사용자의 ID.

    Returns:
        list[schemas.ChatSession]: Pydantic 스키마로 변환된 채팅 세션 목록.
    """
    logger.debug(f"사용자 '{user_id}'의 채팅 세션 목록 조회를 위한 쿼리를 구성합니다.")
    # CTE 1: 각 세션의 첫 사용자 메시지를 찾기 위해 순위를 매김
    ranked_messages_cte = (
        select(
            models.ChatHistory.session_id,
            models.ChatHistory.content,
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

    # CTE 2: 각 세션의 마지막 활동 시간을 찾음
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

    # 최종 쿼리: 두 CTE를 조인하여 필요한 정보를 조합하고 정렬
    stmt = (
        select(
            ranked_messages_cte.c.session_id,
            func.left(ranked_messages_cte.c.content, 50).label(
                "title"
            ),  # 제목은 50자로 제한
            latest_activity_cte.c.last_updated,
        )
        .join(
            latest_activity_cte,
            ranked_messages_cte.c.session_id == latest_activity_cte.c.session_id,
        )
        .where(
            ranked_messages_cte.c.rn == 1
        )  # 순위가 1인, 즉 첫 번째 사용자 메시지만 선택
        .order_by(latest_activity_cte.c.last_updated.desc())  # 최신순으로 정렬
    )

    result = await db_session.execute(stmt)
    sessions = [schemas.ChatSession(**row._asdict()) for row in result]
    logger.debug(f"사용자 '{user_id}'에 대해 {len(sessions)}개의 세션을 조회했습니다.")
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
    # SQLAlchemy 모델 객체(row)를 Pydantic 스키마(ChatMessageInDB)로 변환합니다.
    # .from_orm()은 Pydantic V2의 기능으로, 데이터 유효성 검사와 직렬화를 수행합니다.
    messages = [schemas.ChatMessageInDB.from_orm(row) for row in result.scalars()]
    logger.debug(f"세션 '{session_id}'에서 {len(messages)}개의 메시지를 조회했습니다.")
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
    이는 경쟁 조건(race condition)을 방지하는 데 효과적입니다.

    Args:
        db_session (AsyncSession): 데이터베이스 작업을 위한 세션.
        user_id (int): 프로필을 업데이트할 사용자의 ID.
        profile_text (str): 저장할 프로필 내용.
    """
    logger.debug(f"사용자 '{user_id}'의 프로필 upsert를 시작합니다.")
    stmt = pg_insert(models.UserProfile).values(
        user_id=user_id, profile_text=profile_text.strip()
    )
    # user_id가 충돌할 경우 (이미 레코드가 있을 경우), profile_text 필드를 업데이트합니다.
    update_stmt = stmt.on_conflict_do_update(
        index_elements=[models.UserProfile.user_id],
        set_={"profile_text": stmt.excluded.profile_text},
    )
    await db_session.execute(update_stmt)
    logger.info(f"사용자 '{user_id}'의 프로필을 성공적으로 upsert했습니다.")
