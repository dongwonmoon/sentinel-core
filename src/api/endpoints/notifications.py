"""
API 라우터: 알림 (Notifications)
- /notifications: 읽지 않은 알림 조회
- /notifications/{id}/read: 알림 읽음 처리
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from .. import dependencies, schemas
from ...core.logger import get_logger
from typing import List

router = APIRouter(
    prefix="",
    tags=["Notifications"],
    dependencies=[Depends(dependencies.get_current_user)],
)
logger = get_logger(__name__)


@router.get("", response_model=List[dict])
async def get_unread_notifications(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """현재 사용자의 읽지 않은 모든 알림을 반환합니다."""
    stmt = text(
        """
        SELECT notification_id, message, created_at
        FROM user_notifications
        WHERE user_id = :user_id AND is_read = false
        ORDER BY created_at DESC
        """
    )
    result = await session.execute(stmt, {"user_id": current_user.user_id})
    return [row._asdict() for row in result]


@router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_as_read(
    notification_id: int,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """특정 알림을 읽음 처리합니다."""
    stmt = text(
        """
        UPDATE user_notifications
        SET is_read = true
        WHERE notification_id = :notification_id AND user_id = :user_id
        """
    )
    result = await session.execute(
        stmt,
        {"notification_id": notification_id, "user_id": current_user.user_id},
    )

    if result.rowcount == 0:
        logger.warning(
            f"알림 읽음 처리 실패 (ID: {notification_id}, 사용자: {current_user.username}) - 알림이 없거나 권한이 없음."
        )
        raise HTTPException(
            status_code=404, detail="Notification not found or access denied."
        )
