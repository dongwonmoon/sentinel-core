# -*- coding: utf-8 -*-
"""
벡터 저장소(Vector Store) 컴포넌트의 기본 인터페이스를 정의하는 모듈입니다.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional

from langchain_core.documents import Document


class BaseVectorStore(ABC):
    """
    벡터 저장소의 기본 인터페이스를 정의하는 추상 기본 클래스(Abstract Base Class)입니다.

    이 클래스는 시스템 내에서 사용되는 모든 구체적인 벡터 저장소 클래스(예: `PgVectorStore`, `MilvusVectorStore`)들이
    반드시 구현해야 하는 공통 메서드를 강제합니다. 이를 통해, 어떤 벡터 데이터베이스를 사용하든
    동일한 방식으로 문서를 저장, 검색, 삭제할 수 있어 데이터베이스 교체의 유연성을 확보하고
    코드의 일관성을 유지합니다.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """
        현재 벡터 저장소의 제공자(Provider)를 문자열로 반환해야 합니다.
        (예: "pg_vector", "milvus")

        Returns:
            str: 벡터 저장소 제공자 이름.
        """
        pass

    @abstractmethod
    async def upsert_documents(
        self, documents_data: List[Dict[str, Any]]
    ) -> None:
        """
        문서와 그에 대한 벡터 임베딩을 데이터베이스에 추가하거나 업데이트(Upsert)합니다.

        'Upsert'는 문서가 이미 존재하면 업데이트하고, 존재하지 않으면 새로 추가하는 동작을 의미합니다.
        이 메서드는 문서의 내용, 메타데이터, 임베딩 벡터, 그리고 접근 권한 그룹을 함께 처리해야 합니다.

        Args:
            documents_data (List[Dict[str, Any]]):
                업로드할 문서 데이터의 리스트. 각 딕셔너리는 다음 키를 포함해야 합니다:
                - 'doc_id' (str): 문서의 고유 식별자.
                - 'chunk_text' (str): 분할된 문서의 텍스트 내용.
                - 'embedding' (List[float]): `chunk_text`에 대한 벡터 임베딩.
                - 'metadata' (Dict): 추가적인 메타데이터 (예: 소스 파일 경로).
                - 'permission_groups' (List[str]): 이 문서 청크에 접근할 수 있는 권한 그룹 목록.
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        allowed_groups: List[str],
        k: int = 4,
        doc_ids_filter: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        주어진 쿼리 임베딩과 유사한 문서를 검색합니다.

        이 메서드는 벡터 유사도 검색을 수행하되, 반드시 `allowed_groups`를 기반으로
        접근 권한이 있는 문서들만 결과에 포함시켜야 합니다. 이는 데이터 보안의 핵심적인 부분입니다.

        Args:
            query_embedding (List[float]): 사용자의 검색 쿼리를 임베딩한 벡터.
            allowed_groups (List[str]): 검색을 요청한 사용자가 속한 권한 그룹의 리스트.
            k (int): 반환할 최대 문서 수 (기본값: 4).
            doc_ids_filter (Optional[List[str]]): 검색 범위를 특정 문서 ID들로 제한할 경우 사용.

        Returns:
            List[Dict[str, Any]]: 검색된 문서 청크 정보의 리스트.
                                  각 딕셔너리는 'chunk_text', 'metadata', 'score' 등을 포함합니다.
        """
        pass

    @abstractmethod
    async def delete_documents(self, doc_ids: List[str]) -> int:
        """
        주어진 문서 ID 목록과 일치하는 모든 문서와 그 청크들을 삭제합니다.

        Args:
            doc_ids (List[str]): 삭제할 문서의 고유 ID 리스트.

        Returns:
            int: 성공적으로 삭제된 `document_chunks` 레코드의 수.
        """
        pass
