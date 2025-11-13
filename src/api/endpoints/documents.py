"""
API 라우터: 문서 (Documents)
- /documents: 인덱싱된 문서 관리 (조회, 삭제)
- /upload-and-index: 파일 업로드 및 인덱싱
- /index-github-repo: GitHub 저장소 인덱싱
"""

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
from ...components.vector_stores.base import BaseVectorStore
from ...components.vector_stores.pg_vector_store import PgVectorStore
from ...core.agent import Agent


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post("/upload-and-index", status_code=status.HTTP_202_ACCEPTED)
async def upload_and_index_document(
    file: UploadFile = File(...),
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
):
    """
    파일을 업로드받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    사용자의 권한 그룹이 문서에 태그로 지정됩니다.
    """
    try:
        file_content = await file.read()
        # Celery 작업에 필요한 정보를 전달
        tasks.process_document_indexing.delay(
            file_content=file_content,
            file_name=file.filename,
            permission_groups=current_user.permission_groups,
        )
        return {
            "status": "success",
            "filename": file.filename,
            "message": "File upload successful. Indexing has started in the background.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index-github-repo", status_code=status.HTTP_202_ACCEPTED)
async def index_github_repo(
    body: schemas.GitHubRepoRequest,
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
):
    """
    GitHub 저장소 URL을 받아 Celery에 '백그라운드 인덱싱' 작업을 위임합니다.
    """
    try:
        tasks.process_github_repo_indexing.delay(
            repo_url=str(body.repo_url),
            permission_groups=current_user.permission_groups,
        )
        repo_name = str(body.repo_url).split("/")[-1].replace(".git", "")
        return {
            "status": "success",
            "repo_name": repo_name,
            "message": "GitHub repository cloning and indexing has started in the background.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=dict[str, str])
async def get_indexed_documents(
    current_user: schemas.UserInDB = Depends(dependencies.get_current_user),
    db_session=Depends(dependencies.get_db_session),
):
    """
    현재 사용자가 접근할 수 있는, 인덱싱된 모든 지식 소스를 반환합니다.
    """
    # 직접 DB 세션을 주입받아 쿼리 실행
    try:
        stmt = text(
            """
            SELECT DISTINCT 
                CASE
                    WHEN source_type = 'file-upload' THEN doc_id
                    WHEN source_type = 'file-upload-zip' THEN 'file-upload-' || metadata->>'original_zip' || '/'
                    WHEN source_type = 'github-repo' THEN 'github-repo-' || metadata->>'repo_name' || '/'
                END AS filter_key,
                CASE
                    WHEN source_type = 'file-upload' THEN metadata->>'source'
                    WHEN source_type = 'file-upload-zip' THEN metadata->>'original_zip'
                    WHEN source_type = 'github-repo' THEN metadata->>'repo_name'
                END AS display_name
            FROM documents d
            WHERE d.permission_groups && :allowed_groups -- [보안 필터]
            ORDER BY display_name
            """
        )
        result = await db_session.execute(
            stmt, {"allowed_groups": current_user.permission_groups}
        )
        return {
            row.filter_key: row.display_name for row in result if row.filter_key
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve documents: {e}"
        )


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
    vector_store = agent.vector_store
    if not isinstance(vector_store, PgVectorStore):
        raise HTTPException(
            status_code=501,
            detail="Deletion is only supported for PgVectorStore.",
        )

    try:
        deleted_count = await vector_store.delete_documents(
            doc_id_or_prefix=body.doc_id_or_prefix,
            permission_groups=current_user.permission_groups,
        )
        if deleted_count > 0:
            return {
                "status": "success",
                "message": f"'{body.doc_id_or_prefix}' and related content ({deleted_count} chunks) deleted.",
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No documents found to delete. They may have already been deleted or you may not have permission.",
            )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to delete document: {e}"
        )
