"""
API 라우터: 문서 (Documents)
- /documents: 인덱싱된 문서 관리 (조회, 삭제)
- /upload-and-index: 파일 업로드 및 인덱싱
- /index-github-repo: GitHub 저장소 인덱싱
"""

import json
from typing import List
import io
import zipfile

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    File,
    UploadFile,
    Form,
)
from .. import dependencies, schemas
from ...worker import tasks
from ...worker.celery_app import celery_app
from ...components.vector_stores.pg_vector_store import PgVectorStore
from ...core.agent import Agent
from ...core.logger import get_logger
from ...services import document_service

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

logger = get_logger(__name__)


@router.post("/upload-and-index", status_code=status.HTTP_202_ACCEPTED)
async def upload_and_index_document(
    files: List[UploadFile] = File(...),
    display_name: str = Form(...),
    permission_groups_json: str = Form('["all_users"]'),
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _: None = Depends(dependencies.enforce_document_rate_limit),
):
    """
    파일을 업로드받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    사용자의 권한 그룹이 문서에 태그로 지정됩니다.
    """
    try:
        permission_groups = json.loads(permission_groups_json)
        if not isinstance(permission_groups, list):
            raise ValueError("permission_groups must be a list.")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid permission_groups format: {e}"
        )

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in files:
                # 디렉토리 업로드 시 file.filename은 "folder/file.txt" 형태가 됨
                file_path = file.filename or "unknown_file"

                # 파일 내용을 읽어서 ZIP에 추가
                file_content = await file.read()
                zf.writestr(file_path, file_content)

        # 버퍼의 시작으로 포인터 이동
        zip_buffer.seek(0)
        zip_content_bytes = zip_buffer.getvalue()

        zip_filename_for_task = f"{display_name}.zip"

        task = tasks.process_document_indexing.delay(
            file_content=zip_content_bytes,
            file_name=zip_filename_for_task,
            permission_groups=permission_groups,
            owner_user_id=current_user.user_id,
        )

        logger.info(
            f"파일 {len(files)}개를 '{zip_filename_for_task}' (크기: {len(zip_content_bytes)}B)으로 압축하여"
            f" 인덱싱 작업(권한: {permission_groups}) 위임. Task ID: {task.id}"
        )

        return {
            "status": "success",
            "task_id": task.id,
            "filename": f"{len(files)} files (as zip)",
            "message": f"Successfully uploaded {len(files)} files as a single zip. Indexing started.",
        }

    except Exception as e:
        logger.exception(f"파일 {len(files)}개 업로드 및 ZIP 압축 중 오류 발생.")
        raise HTTPException(
            status_code=500, detail=f"Failed to process file upload: {e}"
        )


@router.post("/index-github-repo", status_code=status.HTTP_202_ACCEPTED)
async def index_github_repo(
    body: schemas.GitHubRepoRequest,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _: None = Depends(dependencies.enforce_document_rate_limit),
):
    """
    GitHub 저장소 URL을 받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    logger.info(
        f"사용자 '{current_user.username}'가 GitHub 저장소 인덱싱 시도: {body.repo_url}"
    )
    try:
        task = tasks.process_github_repo_indexing.delay(
            repo_url=str(body.repo_url),
            permission_groups=current_user.permission_groups,
            owner_user_id=current_user.user_id,
        )
        repo_name = str(body.repo_url).split("/")[-1].replace(".git", "")
        logger.info(
            f"GitHub 저장소 '{repo_name}'에 대한 인덱싱 작업이 Celery 워커에 위임됨."
        )
        return {
            "status": "success",
            "task_id": task.id,
            "repo_name": repo_name,
            "message": "GitHub repository cloning and indexing has started in the background.",
        }
    except Exception as e:
        logger.exception(f"GitHub 저장소 '{body.repo_url}' 인덱싱 중 오류 발생.")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=dict[str, str])
async def get_indexed_documents(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    db_session=Depends(dependencies.get_db_session),
):
    """
    현재 사용자가 접근할 수 있는, 인덱싱된 모든 지식 소스를 반환합니다.
    """
    logger.info(f"사용자 '{current_user.username}'가 인덱싱된 문서 조회를 요청함.")
    try:
        documents = await document_service.list_accessible_documents(
            db_session, current_user.permission_groups
        )
        logger.info(
            f"사용자 '{current_user.username}'를 위해 {len(documents)}개의 인덱싱된 문서 조회 완료."
        )
        return documents
    except Exception as e:
        logger.exception(
            f"사용자 '{current_user.username}'의 인덱싱된 문서 조회 중 오류 발생."
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve documents: {e}"
        )


@router.get("/task-status/{task_id}", status_code=status.HTTP_200_OK)
async def get_task_status(task_id: str):
    """Celery 작업의 현재 상태를 반환합니다."""
    logger.debug(f"작업 상태 확인 요청: {task_id}")
    task_result = celery_app.AsyncResult(task_id)

    status = task_result.status
    result = task_result.result

    if status == "FAILURE":
        logger.warning(f"작업 {task_id} 실패: {result}")
        # result가 Exception 객체일 수 있으므로 문자열로 변환
        result = str(result)

    return {"status": status, "result": result}


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_indexed_document(
    body: schemas.DeleteDocumentRequest,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    agent: Agent = Depends(dependencies.get_agent),
):
    """
    인덱싱된 지식 소스(파일, ZIP, 레포)를 삭제합니다.
    사용자에게 해당 문서를 삭제할 권한이 있어야 합니다.
    """
    logger.info(
        f"사용자 '{current_user.username}'가 문서 삭제 시도: 접두사 '{body.doc_id_or_prefix}'."
    )
    vector_store = agent.vector_store
    if not isinstance(vector_store, PgVectorStore):
        logger.error("삭제는 PgVectorStore에서만 지원되지만, 다른 유형이 발견됨.")
        raise HTTPException(
            status_code=501,
            detail="Deletion is only supported for PgVectorStore.",
        )

    try:
        deleted_count = await document_service.delete_document_by_prefix(
            vector_store,
            body.doc_id_or_prefix,
            current_user.permission_groups,
        )
        if deleted_count > 0:
            logger.info(
                f"접두사 '{body.doc_id_or_prefix}'에 해당하는 문서 {deleted_count}개(청크) 삭제 성공."
            )
            return {
                "status": "success",
                "message": f"'{body.doc_id_or_prefix}' 및 관련 내용 ({deleted_count}개 청크) 삭제됨.",
            }
        else:
            logger.warning(
                f"접두사 '{body.doc_id_or_prefix}'에 해당하는 문서를 찾을 수 없거나 사용자 '{current_user.username}'에게 권한이 없음."
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No documents found to delete. They may have already been deleted or you may not have permission.",
            )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.exception(f"접두사 '{body.doc_id_or_prefix}' 문서 삭제 중 오류 발생.")
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {e}")
