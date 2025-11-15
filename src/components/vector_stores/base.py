from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional

from langchain_core.documents import Document


class BaseVectorStore(ABC):
    """
    벡터 스토어의 기본 인터페이스를 정의하는 추상 기본 클래스입니다.
    모든 구체적인 벡터 스토어 클래스는 이 클래스를 상속받아야 합니다.
    """

    @abstractmethod
    async def upsert_documents(
        self,
        documents: List[Document],
        permission_groups: List[str],
        owner_user_id: int,
    ) -> None:
        """
        문서를 벡터 스토어에 추가하거나 업데이트(upsert)합니다.

        Args:
            documents: 추가 또는 업데이트할 Document 객체의 리스트입니다.
            permission_groups: 이 문서에 접근할 수 있는 권한 그룹의 리스트입니다.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query: str,
        allowed_groups: List[str],
        k: int = 4,
        doc_ids_filter: Optional[List[str]] = None,
        source_type_filter: Optional[str] = None,
    ) -> List[Tuple[Document, float]]:
        """
        주어진 쿼리와 유사한 문서를 검색합니다.
        접근 권한이 있는 그룹의 문서만 검색 결과에 포함됩니다.

        Args:
            query: 검색할 쿼리 텍스트입니다.
            allowed_groups: 사용자가 속한 권한 그룹의 리스트입니다.
            k: 반환할 최대 문서 수입니다.

        Returns:
            (Document, 유사도 점수) 튜플의 리스트를 반환합니다.
        """
        pass

    @abstractmethod
    async def delete_documents(
        self, doc_id_or_prefix: str, permission_groups: List[str]
    ) -> int:
        """
        주어진 doc_id 또는 접두사(prefix)에 해당하는 문서를 삭제합니다.

        Args:
            doc_id_or_prefix: 정확한 문서 ID 또는 'github-repo-name/' 같은 접두사.
            permission_groups: 삭제 권한 검증용 그룹 리스트.

        Returns:
            삭제된 documents 레코드 수.
        """
        pass
