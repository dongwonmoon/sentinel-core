# -*- coding: utf-8 -*-
"""
API 라우터: 채팅 (Chat)

이 모듈은 사용자와 RAG 에이전트 간의 상호작용을 위한 모든 API 엔드포인트를 정의합니다.
-   `/query`: 사용자의 질문을 받아 실시간으로 답변을 스트리밍합니다.
-   `/sessions`: 사용자의 이전 채팅 세션 목록을 조회합니다.
-   `/sessions/{session_id}`: 특정 채팅 세션의 대화 기록을 조회합니다.
-   `/sessions/{session_id}/context`: 특정 세션의 컨텍스트(RAG 필터 등)를 업데이트합니다.
-   `/sessions/{session_id}/attach`: 특정 세션에 임시 파일을 첨부하고 인덱싱합니다.
-   `/profile`: 사용자의 프로필 정보를 조회하고 업데이트합니다.
"""
import json
import redis.asyncio as aioredis
import aiofiles
import os
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    status,
    HTTPException,
    File,
    UploadFile,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from .. import dependencies, schemas
from ...core.agent import Agent
from ...core.logger import get_logger
from ...services import chat_service
from ...worker import tasks
from ...db import models

# 'chat' 기능에 대한 API 라우터를 생성합니다.
# 이 라우터에 등록된 모든 엔드포인트는 '/api/chat' 접두사를 갖게 됩니다.
router = APIRouter()
logger = get_logger(__name__)

# 세션에 첨부된 파일이 임시로 저장될 디렉터리.
# 컨테이너 내부 경로이므로, 볼륨 마운트를 통해 호스트와 연결될 수 있습니다.
SESSION_UPLOAD_DIR = Path("/app/session_uploads")
SESSION_UPLOAD_DIR.mkdir(exist_ok=True)


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
    데이터 조각(토큰, 이벤트 등)을 전송합니다. 이를 통해 사용자는 챗봇의 답변이 생성되는 과정을
    실시간으로 볼 수 있습니다. 대화 내용은 `background_tasks`를 통해 요청-응답 사이클이 끝난 후
    백그라운드에서 비동기적으로 데이터베이스에 저장됩니다.

    Args:
        body (schemas.QueryRequest): 사용자의 질문, 대화 기록, 세션 ID 등을 포함하는 요청 본문.
        background_tasks (BackgroundTasks): FastAPI가 제공하는 백그라운드 작업 관리자.
        current_user: `dependencies.get_current_user`를 통해 주입된, 인증된 사용자 정보.
        _: `dependencies.enforce_chat_rate_limit`를 실행하여 API 호출 속도를 제한. 반환값은 사용하지 않음.
        agent: `dependencies.get_agent`를 통해 주입된, 캐시된 싱글톤 에이전트 인스턴스.
        db_session: `dependencies.get_db_session`을 통해 주입된, DB 작업을 위한 비동기 세션.
        redis: `dependencies.get_redis_client`를 통해 주입된, Redis 클라이언트 인스턴스.

    Returns:
        StreamingResponse: 'text/event-stream' MIME 타입을 가진 스트리밍 응답.
    """
    logger.info(
        f"사용자 '{current_user.username}'(ID: {current_user.user_id})로부터 "
        f"세션 '{body.session_id}'에 대한 쿼리 수신: '{body.query[:100]}...'"
    )

    try:
        # 에이전트(LangGraph)의 입력으로 사용될 딕셔너리를 구성합니다.
        # Redis의 세션 상태, DB의 대화 기록, 사용자 정보 등을 모두 결합합니다.
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
    logger.debug(f"세션 '{body.session_id}'에 대한 에이전트 입력 데이터 구성 완료.")

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
    summary="채팅 세션의 컨텍스트(상태) 업데이트",
)
async def update_session_context(
    session_id: str,
    body: schemas.SessionContextUpdate,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    redis: aioredis.Redis = Depends(dependencies.get_redis_client),
):
    """
    채팅 세션의 상태(예: RAG 문서 필터)를 서버(Redis)에 저장(Stateful)합니다.
    프론트엔드에서 사용자가 RAG 문서 필터를 변경할 때 이 API를 호출하여,
    이후의 모든 RAG 검색에 해당 필터가 적용되도록 합니다.

    Args:
        session_id: 컨텍스트를 업데이트할 세션의 ID.
        body: 업데이트할 컨텍스트 정보 (현재는 `doc_ids_filter`만 포함).
        current_user: 인증된 사용자 정보.
        redis: Redis 클라이언트 인스턴스.
    """
    logger.info(
        f"세션 '{session_id}' (사용자: '{current_user.username}')의 컨텍스트 업데이트 시도."
    )
    session_key = f"session_context:{session_id}"

    try:
        # 기존 컨텍스트를 읽어와서, 새로운 필터 정보로 덮어쓰거나 추가합니다.
        existing_context_raw = await redis.get(session_key)
        context = json.loads(existing_context_raw) if existing_context_raw else {}
        context["doc_ids_filter"] = body.doc_ids_filter

        # 업데이트된 컨텍스트를 Redis에 24시간 만료 시간으로 저장합니다.
        await redis.set(session_key, json.dumps(context), ex=86400)

        logger.debug(f"세션 컨텍스트 업데이트 완료: '{session_key}' = {context}")
        return None  # 성공 시 204 No Content 응답

    except Exception as e:
        logger.error(
            f"세션 '{session_id}'의 컨텍스트 업데이트 실패: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session context.",
        )


@router.post(
    "/sessions/{session_id}/attach",
    status_code=status.HTTP_202_ACCEPTED,
    summary="세션에 임시 파일 첨부 및 인덱싱",
)
async def attach_file_to_session(
    session_id: str,
    file: UploadFile = File(...),
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    db_session: AsyncSession = Depends(dependencies.get_db_session),
    _=Depends(dependencies.enforce_document_rate_limit),
):
    """
    파일을 현재 세션에 '임시'로 첨부하고, 백그라운드에서 인덱싱을 시작합니다.
    이 기능을 통해 사용자는 현재 대화에서만 사용할 문서를 즉시 RAG에 활용할 수 있습니다.

    작업 흐름:
    1.  **파일 저장**: 업로드된 파일을 서버의 임시 디렉터리에 안전하게 저장합니다.
    2.  **DB 레코드 생성**: `session_attachments` 테이블에 파일 정보를 기록하고 상태를 'indexing'으로 설정합니다.
    3.  **비동기 작업 위임**: Celery 워커에게 인덱싱 작업을 위임하고, 즉시 `task_id`를 반환합니다.
    4.  **상태 폴링**: 클라이언트는 이 `task_id`를 사용하여 인덱싱 작업의 진행 상태를 폴링할 수 있습니다.

    Args:
        session_id: 파일을 첨부할 세션의 ID.
        file: 사용자가 업로드한 파일.
        current_user: 인증된 사용자 정보.
        db_session: DB 작업을 위한 세션.
        _: 문서 업로드 속도 제한을 위한 의존성.
    """
    logger.info(
        f"세션 '{session_id}'에 파일 첨부 시도 (사용자: {current_user.username}, 파일: {file.filename})"
    )

    # [보안] 다른 사용자의 파일에 접근하지 못하도록 user_id와 session_id를 경로에 포함하여 격리합니다.
    safe_dir = SESSION_UPLOAD_DIR / str(current_user.user_id) / session_id
    safe_dir.mkdir(parents=True, exist_ok=True)

    # [보안] 경로 탐색 공격(Path Traversal)을 방지하기 위해 파일 이름에서 디렉터리 부분을 제거합니다.
    safe_filename = Path(file.filename).name
    file_path = safe_dir / safe_filename

    try:
        # 대용량 파일을 효율적으로 처리하기 위해 1MB씩 비동기적으로 읽고 씁니다.
        async with aiofiles.open(file_path, "wb") as f:
            while content := await file.read(1024 * 1024):
                await f.write(content)
        logger.debug(f"파일 임시 저장 완료: {file_path}")
    except Exception as e:
        logger.error(f"파일 저장 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="File save failed.")

    try:
        # DB에 'session_attachments' 레코드를 생성하여 파일 정보를 관리합니다.
        new_attachment = models.SessionAttachment(
            session_id=session_id,
            user_id=current_user.user_id,
            file_name=file.filename,
            file_path=str(file_path),  # 워커가 참조할 경로
            status="indexing",
        )
        db_session.add(new_attachment)
        await db_session.commit()
        await db_session.refresh(new_attachment)
        attachment_id = new_attachment.attachment_id
        logger.debug(f"DB 레코드 생성 완료 (Attachment ID: {attachment_id})")
    except Exception as e:
        logger.error(f"첨부파일 DB 레코드 생성 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="DB record creation failed.")

    # Celery 워커에 인덱싱 작업을 위임합니다. API는 즉시 응답을 반환합니다.
    task = tasks.process_session_attachment_indexing.delay(
        attachment_id=attachment_id,
        file_path=str(file_path),
        file_name=file.filename,
    )
    logger.info(f"임시 인덱싱 작업(Task ID: {task.id})을 Celery에 위임했습니다.")

    return {
        "status": "success",
        "task_id": task.id,
        "attachment_id": attachment_id,
        "filename": file.filename,
        "message": f"'{file.filename}' 파일이 첨부되었으며, 백그라운드 인덱싱이 시작되었습니다.",
    }


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
    세션의 제목은 해당 세션의 첫 번째 사용자 메시지로 자동 생성됩니다.

    Args:
        current_user: 인증된 사용자 정보.
        session: DB 작업을 위한 비동기 세션.

    Returns:
        schemas.ChatSessionListResponse: 채팅 세션 목록을 포함하는 응답.
    """
    logger.info(f"사용자 '{current_user.username}'의 채팅 세션 목록 조회를 시작합니다.")
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
    프로필 정보는 에이전트가 사용자에 대한 맥락(예: 역할, 전문 분야)을 파악하여
    더 개인화된 답변을 생성하는 데 사용됩니다.

    Args:
        current_user: 인증된 사용자 정보.
        session: DB 작업을 위한 비동기 세션.

    Returns:
        schemas.UserProfileResponse: 사용자의 프로필 텍스트를 포함하는 응답.
    """
    logger.info(f"사용자 '{current_user.username}'의 프로필 조회를 요청했습니다.")
    profile_text = await chat_service.fetch_user_profile(
        db_session=session, user_id=current_user.user_id
    )
    logger.info(f"사용자 '{current_user.username}'의 프로필을 성공적으로 조회했습니다.")
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
    logger.info(f"사용자 '{current_user.username}'의 프로필 업데이트를 시작합니다.")
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
