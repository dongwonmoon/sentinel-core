"""문서/지식 소스 관리 로직을 담당하는 서비스 계층."""

from __future__ import annotations

import json
from typing import Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..components.vector_stores.pg_vector_store import PgVectorStore
from ..core.logger import get_logger

logger = get_logger(__name__)


async def list_accessible_documents(
    session: AsyncSession, permission_groups: List[str]
) -> Dict[str, str]:
    """사용자 권한에 기반해 필터링된 문서 목록을 반환."""
    stmt = text(
        """
        SELECT doc_id, source_type, metadata
        FROM documents
        WHERE permission_groups && :allowed_groups
        """
    )
    result = await session.execute(stmt, {"allowed_groups": permission_groups})

    documents: Dict[str, str] = {}
    for row in result:
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
            except Exception:  # pragma: no cover - 안전로그
                logger.debug("문서 '%s'의 metadata 바이너리를 파싱하지 못했습니다.", row.doc_id)

        source_type = row.source_type or ""
        filter_key = row.doc_id
        display_name = metadata_dict.get("source") or row.doc_id

        if source_type == "file-upload-zip":
            zip_name = metadata_dict.get("original_zip") or row.doc_id
            if not zip_name:
                zip_name = row.doc_id.split("/")[0].replace("file-upload-", "")
            filter_key = f"file-upload-{zip_name}/"
            display_name = zip_name
        elif source_type == "github-repo":
            repo_name = metadata_dict.get("repo_name")
            if not repo_name:
                repo_name = row.doc_id.split("/", 1)[0].replace("github-repo-", "", 1)
            filter_key = f"github-repo-{repo_name}/"
            display_name = repo_name
        elif source_type == "file-upload":
            filter_key = row.doc_id
            display_name = metadata_dict.get("source") or row.doc_id

        documents[filter_key] = display_name

    return documents


async def delete_document_by_prefix(
    vector_store: PgVectorStore,
    doc_id_or_prefix: str,
    permission_groups: List[str],
) -> int:
    """문서를 접두사 기준으로 삭제하고 삭제된 청크 수를 반환."""
    normalized_prefix = normalize_document_prefix(doc_id_or_prefix)
    logger.debug("문서 삭제 시도 - prefix=%s", normalized_prefix)
    return await vector_store.delete_documents(
        doc_id_or_prefix=normalized_prefix,
        permission_groups=permission_groups,
    )


def normalize_document_prefix(doc_id_or_prefix: str) -> str:
    """사용자 입력을 내부 접두사 규칙에 맞게 조정."""
    prefix = doc_id_or_prefix
    if not prefix.startswith("file-upload-") and not prefix.startswith("github-repo-"):
        prefix = f"file-upload-{prefix}"
    return prefix
