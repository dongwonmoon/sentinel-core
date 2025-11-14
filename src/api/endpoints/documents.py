"""
API 라우터: 문서 (Documents)
- /documents: 인덱싱된 문서 관리 (조회, 삭제)
- /upload-and-index: 파일 업로드 및 인덱싱
- /index-github-repo: GitHub 저장소 인덱싱
"""

import json

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    File,
    UploadFile,
    Form,
)
from sqlalchemy import text

from .. import dependencies, schemas
from ...worker import tasks
from ...worker.celery_app import celery_app
from ...components.vector_stores.base import BaseVectorStore
from ...components.vector_stores.pg_vector_store import PgVectorStore
from ...core.agent import Agent
from ...core.logger import get_logger

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)

logger = get_logger(__name__)


@router.post("/upload-and-index", status_code=status.HTTP_202_ACCEPTED)
async def upload_and_index_document(
    file: UploadFile = File(...),
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    _: None = Depends(dependencies.enforce_document_rate_limit),
):
    """
    파일을 업로드받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    사용자의 권한 그룹이 문서에 태그로 지정됩니다.
    """
    logger.info(
        f"사용자 '{current_user.username}'가 파일 업로드 및 인덱싱 시도: {file.filename}"
    )
    try:
        file_content = await file.read()
        logger.debug(
            f"파일 '{file.filename}' 내용 읽음. 크기: {len(file_content)} 바이트."
        )
        # Celery 작업에 필요한 정보를 전달
        task = tasks.process_document_indexing.delay(
            file_content=file_content,
            file_name=file.filename,
            permission_groups=current_user.permission_groups,
        )
        logger.info(
            f"파일 '{file.filename}'에 대한 인덱싱 작업이 Celery 워커에 위임됨."
        )
        return {
            "status": "success",
            "task_id": task.id,
            "filename": file.filename,
            "message": "File upload successful. Indexing has started in the background.",
        }
    except Exception as e:
        logger.exception(f"파일 '{file.filename}' 업로드 및 인덱싱 중 오류 발생.")
        raise HTTPException(status_code=500, detail=str(e))


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
    # 직접 DB 세션을 주입받아 쿼리 실행
    try:
        stmt = text(
            """
            SELECT doc_id, source_type, metadata
            FROM documents
            WHERE permission_groups && :allowed_groups
            """
        )
        result = await db_session.execute(
            stmt, {"allowed_groups": current_user.permission_groups}
        )
        documents: dict[str, str] = {}
        for row in result:
            # metadata는 JSON/문자열/None 등 다양한 형태일 수 있으므로 안전하게 파싱
            metadata_dict: dict[str, str] = {}
            raw_metadata = row.metadata
            if isinstance(raw_metadata, dict):
                metadata_dict = raw_metadata
            elif isinstance(raw_metadata, str) and raw_metadata:
                try:
                    metadata_dict = json.loads(raw_metadata)
                except json.JSONDecodeError:
                    logger.debug(
                        "문서 '%s'의 metadata를 JSON으로 파싱하지 못했습니다: %s",
                        row.doc_id,
                        raw_metadata[:120],
                    )
            elif isinstance(raw_metadata, (bytes, bytearray, memoryview)):
                try:
                    if isinstance(raw_metadata, memoryview):
                        raw_metadata = raw_metadata.tobytes()
                    metadata_dict = json.loads(raw_metadata.decode("utf-8"))
                except Exception:
                    logger.debug(
                        "문서 '%s'의 metadata 바이너리를 파싱하지 못했습니다.",
                        row.doc_id,
                    )
            source_type = row.source_type or ""
            filter_key = row.doc_id
            display_name = metadata_dict.get("source") or row.doc_id

            if source_type == "file-upload-zip":
                zip_name = metadata_dict.get("original_zip") or row.doc_id
                filter_key = f"file-upload-{zip_name}/"
                display_name = zip_name
            elif source_type == "github-repo":
                repo_name = metadata_dict.get("repo_name")
                if not repo_name:
                    # doc_id는 'github-repo-<repo>/<path>' 형태이므로, 첫 슬래시 이전까지 사용
                    repo_name = row.doc_id.split("/", 1)[0].replace(
                        "github-repo-", "", 1
                    )
                filter_key = f"github-repo-{repo_name}/"
                display_name = repo_name
            elif source_type == "file-upload":
                filter_key = row.doc_id
                display_name = metadata_dict.get("source") or row.doc_id

            documents[filter_key] = display_name

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
        prefix = body.doc_id_or_prefix
        if not prefix.startswith("file-upload-") and not prefix.startswith(
            "github-repo-"
        ):
            prefix = f"file-upload-{prefix}"
        if prefix.endswith("/"):
            logger.debug("접두사 삭제 모드 - prefix=%s", prefix)
        else:
            logger.debug("단일 문서 삭제 모드 - doc_id=%s", prefix)
        deleted_count = await vector_store.delete_documents(
            doc_id_or_prefix=prefix,
            permission_groups=current_user.permission_groups,
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
