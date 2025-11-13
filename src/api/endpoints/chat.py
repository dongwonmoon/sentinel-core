"""
API 라우터: 채팅 (Chat)
- /chat/query: 에이전트에게 질문하고 스트리밍 응답 받기
- /chat/history: 이전 대화 기록 조회
- /chat/message: 대화 메시지 저장
"""

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import dependencies, schemas
from ...core.agent import Agent


router = APIRouter(
    prefix="/chat",
    tags=["Chat"],
)


async def _stream_agent_response(
    agent: Agent,
    inputs: dict,
    db_session: AsyncSession,
) -> AsyncGenerator[str, None]:
    """
    Agent의 응답 스트림을 SSE(Server-Sent Events) 형식으로 변환합니다.
    """
    final_answer = ""
    sources = []

    # Agent의 새로운 메인 메서드 `stream_response`를 호출합니다.
    # 이 메서드는 답변 생성 스트림과 감사 로그 저장을 모두 처리합니다.
    async for event in agent.stream_response(inputs, db_session):
        kind = event["event"]

        # LangGraph의 'on_chat_model_stream' 이벤트에서 LLM 토큰을 받아 클라이언트에 전송
        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            if content:
                final_answer += content
                yield f"data: {json.dumps({'event': 'token', 'data': content})}\\n\n"

        # 그래프 실행이 끝나면, 최종 상태에서 출처(sources) 정보를 추출하여 전송
        elif kind == "on_graph_end":
            final_state = event["data"]["output"]
            if final_state and isinstance(final_state, dict):
                tool_outputs = final_state.get("tool_outputs", {})
                rag_chunks = tool_outputs.get("rag_chunks", [])
                sources = [schemas.Source(**chunk) for chunk in rag_chunks]

                if sources:
                    sources_dict = [s.dict() for s in sources]
                    yield f"data: {json.dumps({'event': 'sources', 'data': sources_dict})}\\n\n"

    # 스트림 종료 이벤트를 전송하여 클라이언트가 연결을 닫도록 함
    yield f"data: {json.dumps({'event': 'end'})}\\n\n"

    # 스트리밍이 모두 끝난 후, AI의 전체 답변을 DB에 저장
    if final_answer:
        await _save_chat_message(
            schemas.ChatMessageBase(role="assistant", content=final_answer),
            session=db_session,
            user_id=inputs["user_id"],  # HACK: user_id를 inputs에서 가져옴
        )


@router.post("/query")
async def query_agent(
    body: schemas.QueryRequest,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    db_session: AsyncSession = Depends(dependencies.get_db_session),
    agent: Agent = Depends(dependencies.get_agent),
):
    """
    에이전트에게 질문하고, 답변을 스트리밍 방식으로 반환합니다.
    """
    # 사용자 메시지를 먼저 DB에 저장
    await _save_chat_message(
        schemas.ChatMessageBase(role="user", content=body.query),
        session=db_session,
        user_id=current_user.user_id,
    )

    inputs = {
        "question": body.query,
        "permission_groups": current_user.permission_groups,
        "top_k": body.top_k,
        "doc_ids_filter": body.doc_ids_filter,
        "chat_history": (
            [msg.dict() for msg in body.chat_history]
            if body.chat_history
            else []
        ),
        "user_id": current_user.user_id,  # HACK: 감사 로그 및 메시지 저장용
    }

    return StreamingResponse(
        _stream_agent_response(agent, inputs, db_session),
        media_type="text/event-stream",
    )


@router.get("/query-stream")
async def query_agent_stream(
    query_request: str,
    token: str,
    agent: Agent = Depends(dependencies.get_agent),
):
    """
    에이전트에게 질문하고, 답변을 스트리밍 방식으로 반환합니다. (GET, EventSource용)
    """
    from ...core.security import verify_token
    from sqlalchemy import text
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 1. 토큰 검증 및 사용자 정보 조회
    token_data = verify_token(token, credentials_exception)
    
    # 2. DB 세션 가져오기 (get_db_session 의존성 수동 처리)
    vector_store = agent.vector_store
    if not isinstance(vector_store, dependencies.PgVectorStore):
        raise HTTPException(
            status_code=500,
            detail="Database session is only available for PgVectorStore.",
        )
    session_local = vector_store.AsyncSessionLocal
    if not session_local:
        raise HTTPException(
            status_code=500, detail="DB session factory is not initialized."
        )
    
    db_session: AsyncSession = session_local()

    try:
        stmt = text("SELECT * FROM users WHERE username = :username")
        result = await db_session.execute(stmt, {"username": token_data.username})
        user_row = result.fetchone()

        if user_row is None:
            raise credentials_exception
        
        current_user = schemas.UserInDB(**user_row._asdict())
        if not current_user.is_active:
            raise HTTPException(status_code=400, detail="Inactive user")

        # 3. 요청 파싱
        try:
            body = schemas.QueryRequest.parse_obj(json.loads(query_request))
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid query_request format")

        # 4. 사용자 메시지 DB에 저장
        await _save_chat_message(
            schemas.ChatMessageBase(role="user", content=body.query),
            session=db_session,
            user_id=current_user.user_id,
        )
        await db_session.commit() # 수동 커밋 필요

        # 5. 스트리밍 로직 호출
        inputs = {
            "question": body.query,
            "permission_groups": current_user.permission_groups,
            "top_k": body.top_k,
            "doc_ids_filter": body.doc_ids_filter,
            "chat_history": (
                [msg.dict() for msg in body.chat_history]
                if body.chat_history
                else []
            ),
            "user_id": current_user.user_id,
        }

        return StreamingResponse(
            _stream_agent_response(agent, inputs, db_session),
            media_type="text/event-stream",
        )
    except Exception:
        await db_session.rollback()
        raise
    finally:
        await db_session.close()


@router.get("/history", response_model=schemas.ChatHistoryResponse)
async def get_chat_history(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """현재 로그인한 사용자의 모든 채팅 기록을 시간순으로 가져옵니다."""
    from sqlalchemy import text

    stmt = text(
        """
        SELECT role, content, created_at 
        FROM chat_history
        WHERE user_id = :user_id 
        ORDER BY created_at ASC
        """
    )
    result = await session.execute(stmt, {"user_id": current_user.user_id})
    messages = [schemas.ChatMessageInDB(**row._asdict()) for row in result]
    return schemas.ChatHistoryResponse(messages=messages)


async def _save_chat_message(
    message: schemas.ChatMessageBase,
    session: AsyncSession,
    user_id: int,
):
    """'user' 또는 'assistant'의 단일 메시지를 DB에 저장하는 헬퍼 함수."""
    from sqlalchemy import text

    try:
        stmt = text(
            """
            INSERT INTO chat_history (user_id, role, content)
            VALUES (:user_id, :role, :content)
            """
        )
        await session.execute(
            stmt,
            {
                "user_id": user_id,
                "role": message.role,
                "content": message.content,
            },
        )
    except Exception as e:
        # 이 함수는 스트림의 일부로 호출되므로, 실패 시 HTTP 예외를 발생시키지 않고 로깅만 합니다.
        print(f"Error saving chat message: {e}")
