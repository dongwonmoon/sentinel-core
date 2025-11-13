from abc import ABC, abstractmethod
from typing import List, Tuple
from langchain_core.documents import Document


class BaseReranker(ABC):
    """
    Reranker의 기본 인터페이스를 정의하는 추상 기본 클래스입니다.
    모든 구체적인 Reranker 클래스는 이 클래스를 상속받아야 합니다.
    """

    @abstractmethod
    def rerank(
        self,
        query: str,
        documents: List[Tuple[Document, float]],
    ) -> List[Tuple[Document, float]]:
        """
        주어진 쿼리를 기반으로 검색된 문서 목록의 순위를 재조정합니다.

        Args:
            query: 사용자의 원본 쿼리 텍스트입니다.
            documents: (Document, 초기 점수) 튜플의 리스트입니다.

        Returns:
            순위가 재조정된 (Document, 재조정된 점수) 튜플의 리스트를 반환합니다.
        """
        pass
