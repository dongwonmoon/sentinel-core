from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from .. import dependencies, schemas
from ...core.logger import get_logger
import json

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(dependencies.get_admin_user)],
)
logger = get_logger(__name__)


async def _log_admin_action(
    session: AsyncSession,
    actor_user_id: int,
    action: str,
    target_id: str,
    old_value: dict = None,
    new_value: dict = None,
):
    stmt = text(
        """
        INSERT INTO admin_audit_log (actor_user_id, action, target_id, old_value, new_value)
        VALUES (:actor, :action, :target, :old, :new)
        """
    )
    await session.execute(
        stmt,
        {
            "actor": actor_user_id,
            "action": action,
            "target": target_id,
            "old": json.dumps(old_value) if old_value else None,
            "new": json.dumps(new_value) if new_value else None,
        },
    )


@router.put("/users/{user_id}/permissions", response_model=schemas.User)
async def update_user_permissions(
    user_id: int,
    body: dict,  # e.g., {"groups": ["developer", "all_users"]}
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    new_groups = body.get("groups", [])
    old_user_raw = await session.execute(
        text("SELECT * FROM users WHERE user_id = :id"), {"id": user_id}
    )
    old_user = old_user_raw.fetchone()
    if not old_user:
        raise HTTPException(status_code=404, detail="User not found")
    old_groups = old_user._asdict().get("permission_groups", [])

    # 사용자 권한 업데이트
    stmt = text(
        "UPDATE users SET permission_groups = :groups WHERE user_id = :id RETURNING *"
    )
    result = await session.execute(stmt, {"groups": new_groups, "id": user_id})
    updated_user = result.fetchone()

    await _log_admin_action(
        session,
        admin_user.user_id,
        "update_user_permissions",
        f"user_id:{user_id}",
        {"groups": old_groups},
        {"groups": new_groups},
    )

    logger.info(
        f"Admin '{admin_user.username}'가 사용자 ID {user_id}의 권한을 {new_groups}로 변경."
    )
    return schemas.User(**updated_user._asdict())


@router.get("/audit-logs/admin")
async def get_admin_audit_logs(
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    result = await session.execute(
        text("SELECT * FROM admin_audit_log ORDER BY created_at DESC LIMIT 100")
    )
    return result.fetchall()


@router.get("/audit-logs/agent/{session_id}")
async def get_agent_audit_logs(
    session_id: str, session: AsyncSession = Depends(dependencies.get_db_session)
):
    stmt = text(
        "SELECT * FROM agent_audit_log WHERE session_id = :sid ORDER BY created_at ASC"
    )
    result = await session.execute(stmt, {"sid": session_id})
    return result.fetchall()


@router.put("/documents/{doc_id}/permissions")
async def update_document_permissions(
    doc_id: str,
    body: dict,  # e.g., {"groups": ["it", "all_users"]}
    admin_user: schemas.UserInDB = Depends(dependencies.get_admin_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    # ... (구현: user_id 대신 doc_id를 사용하고 documents 테이블을 업데이트) ...
    # ... (감사 로그 기록 로직 포함) ...
    pass  # (구현 필요)
