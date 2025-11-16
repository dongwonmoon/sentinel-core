# -*- coding: utf-8 -*-
"""
API 라우터: 관리자 (Admin)

이 모듈은 시스템 관리를 위한 API 엔드포인트를 정의합니다.
모든 엔드포인트는 `get_admin_user` 의존성을 통해 관리자 권한을 가진 사용자만 접근할 수 있도록 보호됩니다.
"""

import json
from typing import Dict, Any, Optional, List
import sqlalchemy as sa
from sqlalchemy import select

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .. import dependencies, schemas
from ...core.logger import get_logger
from ...db import models
from ...worker import tasks

logger = get_logger(__name__)

# `dependencies=[Depends(dependencies.get_admin_user)]` 설정을 통해
# 이 라우터에 속한 모든 API는 요청 시 관리자 권한을 자동으로 검증합니다.
router = APIRouter(
    prefix="",
    tags=["Admin"],
    dependencies=[Depends(dependencies.get_admin_user)],
)


async def _log_admin_action(
    session: AsyncSession,
    actor_user_id: int,
    action: str,
    target_id: str,
    old_value: Optional[Dict[str, Any]] = None,
    new_value: Optional[Dict[str, Any]] = None,
):
    """[헬퍼 함수] 관리자의 주요 행위를 'admin_audit_log' 테이블에 기록합니다."""
    logger.debug(
        f"관리자 감사 로그 기록: 행위자 ID={actor_user_id}, 액션='{action}', 대상='{target_id}'"
    )
    stmt = text(
        """
        INSERT INTO admin_audit_log (actor_user_id, action, target_id, old_value, new_value)
        VALUES (:actor_user_id, :action, :target_id, :old_value, :new_value)
    """
    )
    await session.execute(
        stmt,
        {
            "actor_user_id": actor_user_id,
            "action": action,
            "target_id": target_id,
            "old_value": json.dumps(old_value) if old_value else None,
            "new_value": json.dumps(new_value) if new_value else None,
        },
    )


@router.put(
    "/users/{user_id}/permissions",
    response_model=schemas.User,
    summary="사용자 권한 업데이트",
)
async def update_user_permissions(
    user_id: int,
    body: schemas.UpdatePermissionsRequest,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> schemas.User:
    """
    특정 사용자의 권한 그룹을 업데이트합니다.
    """
    logger.info(
        f"관리자 '{admin_user.username}'가 사용자 ID {user_id}의 권한 업데이트를 시도합니다."
    )

    # 1. 대상 사용자의 현재 상태를 조회합니다 (감사 로그 기록용).
    result = await session.execute(
        text("SELECT * FROM users WHERE user_id = :id"), {"id": user_id}
    )
    old_user = result.fetchone()
    if not old_user:
        logger.warning(f"권한 업데이트 실패: 사용자 ID {user_id}를 찾을 수 없습니다.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    old_groups = old_user._asdict().get("permission_groups", [])
    new_groups = body.groups

    # 2. 사용자 권한을 업데이트하는 SQL을 실행합니다.
    stmt = text(
        "UPDATE users SET permission_groups = :groups WHERE user_id = :id RETURNING *"
    )
    result = await session.execute(stmt, {"groups": new_groups, "id": user_id})
    updated_user = result.fetchone()

    if not updated_user:
        # 이 경우는 거의 발생하지 않지만, 방어적으로 처리합니다.
        logger.error(
            f"사용자 ID {user_id}의 권한 업데이트 후 사용자 정보를 가져오지 못했습니다."
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve updated user data.",
        )

    # 3. 관리자 행위 감사 로그를 기록합니다.
    await _log_admin_action(
        session=session,
        actor_user_id=admin_user.user_id,
        action="update_user_permissions",
        target_id=f"user_id:{user_id}",
        old_value={"groups": old_groups},
        new_value={"groups": new_groups},
    )

    logger.info(
        f"관리자 '{admin_user.username}'가 사용자 ID {user_id}의 권한을 {old_groups}에서 {new_groups}(으)로 변경했습니다."
    )
    return schemas.User(**updated_user._asdict())


@router.post(
    "/tools",
    response_model=schemas.ToolResponse,
    status_code=status.HTTP_201_CREATED,
    summary="새로운 동적 도구 등록",
)
async def create_registered_tool(
    tool_data: schemas.ToolCreate,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """(Admin) 에이전트가 사용할 새 동적 도구를 DB에 등록합니다."""
    logger.info(
        f"관리자 '{admin_user.username}'가 새 도구 '{tool_data.name}' 등록을 시도합니다."
    )
    try:
        new_tool = models.RegisteredTool(**tool_data.model_dump())
        session.add(new_tool)
        await session.commit()
        await session.refresh(new_tool)

        await _log_admin_action(
            session=session,
            actor_user_id=admin_user.user_id,
            action="create_tool",
            target_id=f"tool_id:{new_tool.tool_id}",
            new_value=tool_data.model_dump(),
        )
        return new_tool
    except sa.exc.IntegrityError:
        logger.warning(f"도구 등록 실패: '{tool_data.name}' 이름이 이미 존재합니다.")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tool with this name already exists.",
        )


@router.get(
    "/tools",
    response_model=List[schemas.ToolResponse],
    summary="등록된 모든 동적 도구 조회",
)
async def get_registered_tools(
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """(Admin) DB에 등록된 모든 동적 도구 목록을 조회합니다."""
    result = await session.execute(
        select(models.RegisteredTool).order_by(models.RegisteredTool.name)
    )
    return result.scalars().all()


@router.put(
    "/tools/{tool_id}",
    response_model=schemas.ToolResponse,
    summary="동적 도구 정보 수정",
)
async def update_registered_tool(
    tool_id: int,
    tool_data: schemas.ToolUpdate,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """(Admin) 기존에 등록된 동적 도구의 정보를 수정합니다."""
    tool = await session.get(models.RegisteredTool, tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found"
        )

    old_data = schemas.ToolResponse.from_orm(tool).model_dump()

    # Update
    for key, value in tool_data.model_dump().items():
        setattr(tool, key, value)

    session.add(tool)
    await session.commit()
    await session.refresh(tool)

    await _log_admin_action(
        session=session,
        actor_user_id=admin_user.user_id,
        action="update_tool",
        target_id=f"tool_id:{tool_id}",
        old_value=old_data,
        new_value=tool_data.model_dump(),
    )
    return tool


@router.delete(
    "/tools/{tool_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="동적 도구 삭제",
)
async def delete_registered_tool(
    tool_id: int,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """(Admin) 등록된 동적 도구를 DB에서 삭제합니다."""
    tool = await session.get(models.RegisteredTool, tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found"
        )

    await session.delete(tool)
    await session.commit()

    await _log_admin_action(
        session=session,
        actor_user_id=admin_user.user_id,
        action="delete_tool",
        target_id=f"tool_id:{tool_id}",
        old_value={"name": tool.name},
    )
    return None


@router.get(
    "/audit-logs/admin",
    response_model=list[schemas.AdminAuditLog],
    summary="관리자 감사 로그 조회",
)
async def get_admin_audit_logs(
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> list:
    """
    관리자 행위 감사 로그를 최신순으로 100개 조회합니다.
    """
    logger.info("관리자 감사 로그 조회를 요청했습니다.")
    result = await session.execute(
        text("SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT 100")
    )
    logs = result.fetchall()
    logger.info(f"{len(logs)}개의 관리자 감사 로그를 조회했습니다.")
    return logs


@router.get(
    "/audit-logs/agent/{session_id}",
    response_model=list[schemas.AgentAuditLog],
    summary="에이전트 감사 로그 조회",
)
async def get_agent_audit_logs(
    session_id: str,
    session: AsyncSession = Depends(dependencies.get_db_session),
) -> list:
    """
    특정 세션 ID에 대한 에이전트의 전체 작동 기록(감사 로그)을 시간순으로 조회합니다.
    디버깅에 매우 유용합니다.
    """
    logger.info(
        f"세션 ID '{session_id}'에 대한 에이전트 감사 로그 조회를 요청했습니다."
    )
    stmt = text(
        "SELECT * FROM agent_audit_log WHERE session_id = :sid ORDER BY created_at ASC"
    )
    result = await session.execute(stmt, {"sid": session_id})
    logs = result.fetchall()
    logger.info(
        f"세션 ID '{session_id}'에 대해 {len(logs)}개의 에이전트 감사 로그를 조회했습니다."
    )
    return logs


@router.get(
    "/pending_attachments",
    response_model=List[schemas.SessionAttachment],
    summary="[신규] (거버넌스) KB 승인 대기 중인 첨부파일 목록 조회",
)
async def get_pending_attachments(
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    db_session: AsyncSession = Depends(dependencies.get_db_session),
):
    """(Admin) '영구 지식(KB)'로 승인 대기 중인 파일 목록을 조회합니다."""
    stmt = (
        select(models.SessionAttachment)
        .where(models.SessionAttachment.status == "pending_review")
        .order_by(models.SessionAttachment.created_at.asc())
    )
    result = await db_session.execute(stmt)
    return result.scalars().all()


@router.post(
    "/approve_promotion/{attachment_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="(거버넌스) KB 승인 요청 '승인'",
)
async def approve_document_promotion(
    attachment_id: int,
    body: schemas.PromotionApprovalRequest,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    db_session: AsyncSession = Depends(dependencies.get_db_session),
):
    """
    (Admin) 사용자의 '지식 승격' 요청을 승인합니다.
    승인 시, '임시' 청크/임베딩을 '영구' KB로 복사하는 Celery 태스크가 호출됩니다.
    """
    attachment = await db_session.get(models.SessionAttachment, attachment_id)
    if not attachment or attachment.status != "pending_review":
        raise HTTPException(
            status_code=404,
            detail="Attachment not found or not pending review.",
        )

    # 관리자가 확정한 ID가 영구 KB에 이미 있는지 재확인
    existing_doc = await db_session.get(models.Document, body.kb_doc_id)
    if existing_doc:
        raise HTTPException(
            status_code=409,
            detail=f"A document with the final ID '{body.kb_doc_id}' already exists.",
        )

    # 1. Celery 태스크 호출 (무거운 DB 복사 작업 위임)
    task = tasks.promote_to_kb.delay(
        attachment_id=attachment_id,
        kb_doc_id=body.kb_doc_id,
        permission_groups=body.permission_groups,
        admin_user_id=admin_user.user_id,
    )

    # 2. 원본 첨부파일 상태를 'promoting'(승격 진행 중)으로 변경
    attachment.status = "promoting"
    db_session.add(attachment)

    # 3. 감사 로그 기록
    await _log_admin_action(
        session=db_session,
        actor_user_id=admin_user.user_id,
        action="approve_promotion",
        target_id=f"attachment_id:{attachment_id}",
        new_value={
            "approved_kb_doc_id": body.kb_doc_id,
            "permission_groups": body.permission_groups,
        },
    )

    await db_session.commit()

    return {"status": "promoting", "task_id": task.id}


@router.post(
    "/reject_promotion/{attachment_id}",
    status_code=status.HTTP_200_OK,
    summary="(거버넌스) KB 승인 요청 '반려'",
)
async def reject_document_promotion(
    attachment_id: int,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    db_session: AsyncSession = Depends(dependencies.get_db_session),
):
    """(Admin) 사용자의 '지식 승격' 요청을 반려합니다."""
    attachment = await db_session.get(models.SessionAttachment, attachment_id)
    if not attachment or attachment.status != "pending_review":
        raise HTTPException(
            status_code=404,
            detail="Attachment not found or not pending review.",
        )

    # 1. 상태를 'rejected'(반려됨)로 변경
    attachment.status = "rejected"
    db_session.add(attachment)

    # 2. 감사 로그 기록
    await _log_admin_action(
        session=db_session,
        actor_user_id=admin_user.user_id,
        action="reject_promotion",
        target_id=f"attachment_id:{attachment_id}",
    )

    await db_session.commit()

    # 3. 반려 사유를 요청자에게 알림
    tasks.notify_user.delay(
        user_id=attachment.user_id,
        message=f"요청하신 문서 '{attachment.file_name}'의 KB 등록이 관리자에 의해 반려되었습니다.",
    )

    return {"status": "rejected"}
