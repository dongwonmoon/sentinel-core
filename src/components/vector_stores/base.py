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
    async def search(
        self,
        query: str,
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
    async def search_session_attachments(
        self,
        query: str,
        session_id: str,
        k: int = 4,
    ) -> List[Dict[str, Any]]:
        pass
