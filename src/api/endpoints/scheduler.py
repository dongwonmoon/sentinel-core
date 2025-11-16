"""
API 라우터: 스케줄러 (Scheduler)
- /scheduler/tasks: 사용자 정의 반복 작업 관리 (CRUD)
"""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from .. import dependencies, schemas
from ...core.logger import get_logger
from typing import List
from croniter import croniter

router = APIRouter(
    prefix="/scheduler",
    tags=["Scheduler"],
    dependencies=[Depends(dependencies.get_current_user)],
)
logger = get_logger(__name__)


@router.post(
    "/tasks",
    response_model=schemas.TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_task(
    task_data: schemas.TaskCreate,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """새로운 반복 작업을 등록합니다."""

    # 1. Crontab 유효성 검사
    if not croniter.is_valid(task_data.schedule):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid crontab format: {task_data.schedule}",
        )

    # 2. (중요) 작업 유형(task_name) 및 인자(kwargs) 유효성 검사
    if task_data.task_name == "run_scheduled_github_summary":
        if not task_data.task_kwargs.get("repo_url"):
            raise HTTPException(
                status_code=400, detail="Missing 'repo_url' in task_kwargs"
            )
    else:
        raise HTTPException(
            status_code=400, detail=f"Invalid task_name: {task_data.task_name}"
        )

    stmt = text(
        """
        INSERT INTO scheduled_tasks (user_id, task_name, schedule, task_kwargs, is_active)
        VALUES (:user_id, :task_name, :schedule, :task_kwargs, true)
        RETURNING *
        """
    )
    result = await session.execute(
        stmt,
        {
            "user_id": current_user.user_id,
            "task_name": task_data.task_name,
            "schedule": task_data.schedule,
            "task_kwargs": json.dumps(task_data.task_kwargs),
        },
    )
    new_task = result.fetchone()
    return new_task._asdict()


@router.get("/tasks", response_model=List[schemas.TaskResponse])
async def get_scheduled_tasks(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """현재 사용자가 등록한 모든 반복 작업을 조회합니다."""
    stmt = text(
        "SELECT * FROM scheduled_tasks WHERE user_id = :user_id ORDER BY created_at DESC"
    )
    result = await session.execute(stmt, {"user_id": current_user.user_id})
    return [row._asdict() for row in result]


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_task(
    task_id: int,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    session: AsyncSession = Depends(dependencies.get_db_session),
):
    """반복 작업을 삭제합니다."""
    stmt = text(
        "DELETE FROM scheduled_tasks WHERE task_id = :task_id AND user_id = :user_id"
    )
    result = await session.execute(
        stmt, {"task_id": task_id, "user_id": current_user.user_id}
    )
    if result.rowcount == 0:
        raise HTTPException(
            status_code=404, detail="Task not found or access denied."
        )
