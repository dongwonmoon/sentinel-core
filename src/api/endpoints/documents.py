# -*- coding: utf-8 -*-
"""
API 라우터: 문서 (Documents)

이 모듈은 지식 소스(문서, GitHub 리포지토리 등)의 업로드, 인덱싱, 조회, 삭제 등
문서 관리와 관련된 모든 API 엔드포인트를 정의합니다.
"""

import json
from typing import List
import io
import zipfile

from fastapi import (
    APIRouter, Depends, HTTPException, status, File, UploadFile, Form
)
from celery.result import AsyncResult

from .. import dependencies, schemas
from ...worker import tasks
from ...worker.celery_app import celery_app
from ...core.logger import get_logger
from ...services import document_service

# '/documents' 접두사를 가진 APIRouter를 생성합니다.
# 모든 엔드포인트는 기본적으로 `get_current_user` 의존성을 통해 인증된 사용자만 접근 가능합니다.
router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
    dependencies=[Depends(dependencies.get_current_user)],
)
logger = get_logger(__name__)


@router.post("/upload-and-index", status_code=status.HTTP_202_ACCEPTED, summary="파일 업로드 및 인덱싱 시작")
async def upload_and_index_document(
    files: List[UploadFile] = File(...),
    display_name: str = Form(...),
    permission_groups_json: str = Form('["all_users"]'),
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _ = Depends(dependencies.enforce_document_rate_limit),
):
    """
    하나 이상의 파일을 업로드받아 메모리 내에서 ZIP 파일로 압축한 후,
    Celery 워커에게 '백그라운드 인덱싱' 작업을 위임합니다.
    
    이 방식은 여러 파일을 단일 작업으로 처리할 수 있게 하여 효율적입니다.
    HTTP 202 Accepted 상태 코드는 요청이 수락되었으며, 비동기적으로 처리될 것임을 의미합니다.

    Args:
        files (List[UploadFile]): 업로드된 파일 목록.
        display_name (str): 사용자가 지정한 이 업로드의 표시 이름 (ZIP 파일 이름으로 사용됨).
        permission_groups_json (str): 문서에 적용할 권한 그룹 목록 (JSON 문자열 형태).
        current_user (schemas.UserInDB): 현재 인증된 사용자 정보.
    """
    try:
        permission_groups = json.loads(permission_groups_json)
        if not isinstance(permission_groups, list):
            raise ValueError("permission_groups는 반드시 리스트 형태여야 합니다.")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"잘못된 형식의 permission_groups_json 수신: {permission_groups_json}, 오류: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"잘못된 JSON 형식의 권한 그룹입니다: {e}")

    if not files:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="업로드된 파일이 없습니다.")

    logger.info(f"사용자 '{current_user.username}'로부터 '{display_name}' 이름으로 {len(files)}개 파일 업로드 요청 수신.")

    try:
        # 메모리 내에서 ZIP 파일을 생성하기 위해 BytesIO 버퍼를 사용합니다.
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in files:
                file_path = file.filename or "unknown_file"
                file_content = await file.read()
                zf.writestr(file_path, file_content)
                logger.debug(f"'{file_path}' ({len(file_content)} 바이트)를 ZIP 버퍼에 추가했습니다.")
        
        zip_buffer.seek(0)
        zip_content_bytes = zip_buffer.getvalue()
        zip_filename_for_task = f"{display_name}.zip"

        # Celery 태스크를 큐에 발행합니다. `.delay()`는 작업을 비동기적으로 실행하도록 요청합니다.
        task = tasks.process_document_indexing.delay(
            file_content=zip_content_bytes,
            file_name=zip_filename_for_task,
            permission_groups=permission_groups,
            owner_user_id=current_user.user_id,
        )
        logger.info(f"인덱싱 작업(Task ID: {task.id})을 Celery에 성공적으로 위임했습니다. (파일: {zip_filename_for_task})")

        return {
            "status": "success",
            "task_id": task.id,
            "filename": zip_filename_for_task,
            "message": f"'{display_name}'({len(files)}개 파일) 업로드 성공. 백그라운드에서 인덱싱이 시작되었습니다.",
        }
    except Exception as e:
        logger.exception(f"파일 업로드 및 ZIP 압축 중 예기치 않은 오류 발생 (사용자: {current_user.username})")
        raise HTTPException(status_code=500, detail=f"파일 업로드 처리 중 서버 오류가 발생했습니다: {e}")


@router.post("/index-github-repo", status_code=status.HTTP_202_ACCEPTED, summary="GitHub 리포지토리 인덱싱 시작")
async def index_github_repo(
    body: schemas.GitHubRepoRequest,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _ = Depends(dependencies.enforce_document_rate_limit),
):
    """
    GitHub 저장소 URL을 받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    repo_url = str(body.repo_url)
    logger.info(f"사용자 '{current_user.username}'로부터 GitHub 리포지토리 인덱싱 요청 수신: {repo_url}")
    
    try:
        task = tasks.process_github_repo_indexing.delay(
            repo_url=repo_url,
            permission_groups=current_user.permission_groups,
            owner_user_id=current_user.user_id,
        )
        repo_name = repo_url.split("/")[-1].replace(".git", "")
        logger.info(f"GitHub 리포지토리 '{repo_name}' 인덱싱 작업(Task ID: {task.id})을 Celery에 성공적으로 위임했습니다.")
        return {
            "status": "success",
            "task_id": task.id,
            "repo_name": repo_name,
            "message": "GitHub 리포지토리 클론 및 인덱싱 작업이 백그라운드에서 시작되었습니다.",
        }
    except Exception as e:
        logger.exception(f"GitHub 리포지토리 '{repo_url}' 인덱싱 작업 위임 중 예기치 않은 오류 발생.")
        raise HTTPException(status_code=500, detail=f"작업 위임 중 서버 오류가 발생했습니다: {e}")


@router.get("", response_model=List[schemas.DocumentResponse], summary="인덱싱된 문서 목록 조회")
async def get_indexed_documents(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    db_session=Depends(dependencies.get_db_session),
):
    """
    현재 사용자가 접근할 수 있는, 인덱싱된 모든 지식 소스 목록을 반환합니다.
    """
    logger.info(f"사용자 '{current_user.username}'의 접근 가능한 문서 목록 조회를 요청했습니다.")
    try:
        documents = await document_service.list_accessible_documents(db_session, current_user.permission_groups)
        logger.info(f"사용자 '{current_user.username}'를 위해 {len(documents)}개의 문서를 성공적으로 조회했습니다.")
        return documents
    except Exception as e:
        logger.exception(f"인덱싱된 문서 조회 중 예기치 않은 오류 발생 (사용자: {current_user.username}).")
        raise HTTPException(status_code=500, detail=f"문서 조회 중 서버 오류가 발생했습니다: {e}")


@router.get("/task-status/{task_id}", response_model=schemas.TaskStatusResponse, summary="백그라운드 작업 상태 조회")
async def get_task_status(task_id: str):
    """Celery 작업의 현재 상태와 결과를 반환합니다."""
    logger.debug(f"작업 상태 확인 요청: Task ID='{task_id}'")
    task_result = AsyncResult(task_id, app=celery_app)

    status = task_result.status
    result = task_result.result

    if status == "FAILURE":
        logger.warning(f"실패한 작업({task_id})의 상태가 조회되었습니다. 결과: {result}")
        # result가 Exception 객체일 수 있으므로 안전하게 문자열로 변환합니다.
        result = str(result)
    
    return {"task_id": task_id, "status": status, "result": result}


@router.delete("", status_code=status.HTTP_200_OK, summary="인덱싱된 문서 삭제")
async def delete_indexed_document(
    body: schemas.DeleteDocumentRequest,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    db_session=Depends(dependencies.get_db_session),
):
    """
    ID 또는 접두사를 기준으로 인덱싱된 지식 소스(파일, ZIP, 레포)를 삭제합니다.
    사용자는 자신이 소유한 문서만 삭제할 수 있습니다.
    """
    doc_id_or_prefix = body.doc_id_or_prefix
    logger.info(f"사용자 '{current_user.username}'(ID: {current_user.user_id})가 문서 삭제를 시도합니다: '{doc_id_or_prefix}'")

    try:
        deleted_count = await document_service.delete_documents_by_id_or_prefix(
            db_session=db_session,
            doc_id_or_prefix=doc_id_or_prefix,
            user_id=current_user.user_id,
        )
        if deleted_count > 0:
            logger.info(f"'{doc_id_or_prefix}'에 해당하는 문서 {deleted_count}개를 성공적으로 삭제했습니다.")
            return {
                "status": "success",
                "message": f"'{doc_id_or_prefix}' 및 관련 데이터가 성공적으로 삭제되었습니다.",
                "deleted_count": deleted_count,
            }
        else:
            logger.warning(f"삭제할 문서를 찾지 못했습니다: '{doc_id_or_prefix}'. 이미 삭제되었거나 소유자가 아닐 수 있습니다.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="삭제할 문서를 찾을 수 없습니다. 이미 삭제되었거나 소유자가 아닐 수 있습니다.",
            )
    except HTTPException:
        # 이미 처리된 HTTP 예외는 그대로 다시 발생시킵니다.
        raise
    except Exception as e:
        logger.exception(f"문서 삭제 중 예기치 않은 오류 발생: '{doc_id_or_prefix}'")
        raise HTTPException(status_code=500, detail=f"문서 삭제 중 서버 오류가 발생했습니다: {e}")
