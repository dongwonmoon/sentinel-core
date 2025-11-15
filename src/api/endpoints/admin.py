# -*- coding: utf-8 -*-
"""
API 라우터: 관리자 (Admin)

이 모듈은 시스템 관리를 위한 API 엔드포인트를 정의합니다.
모든 엔드포인트는 `get_admin_user` 의존성을 통해 관리자 권한을 가진 사용자만 접근할 수 있도록 보호됩니다.
"""

import json
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .. import dependencies, schemas
from ...core.logger import get_logger

logger = get_logger(__name__)

# '/admin' 접두사를 가진 APIRouter를 생성합니다.
# `dependencies=[Depends(dependencies.get_admin_user)]` 설정을 통해
# 이 라우터에 속한 모든 API는 요청 시 관리자 권한을 자동으로 검증합니다.
router = APIRouter(
    prefix="/admin",
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
        logger.warning(
            f"권한 업데이트 실패: 사용자 ID {user_id}를 찾을 수 없습니다."
        )
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


@router.put(
    "/documents/{doc_id}/permissions", summary="문서 권한 업데이트 (미구현)"
)
async def update_document_permissions(
    doc_id: str,
    body: schemas.UpdatePermissionsRequest,
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """
    특정 문서(doc_id)의 접근 권한 그룹을 업데이트합니다.
    (참고: 이 기능은 현재 구현되지 않았습니다.)
    """
    logger.warning(
        f"미구현된 API 'update_document_permissions'가 호출되었습니다 (doc_id: {doc_id})."
    )
    # TODO: 사용자 권한 업데이트와 유사하게 문서의 `permission_groups`를 업데이트하는 로직 구현
    # 1. `documents` 테이블에서 `doc_id`로 기존 문서 조회
    # 2. `UPDATE` 쿼리로 `permission_groups` 필드 변경
    # 3. `_log_admin_action`을 호출하여 감사 로그 기록
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="This feature is not yet implemented.",
    )
