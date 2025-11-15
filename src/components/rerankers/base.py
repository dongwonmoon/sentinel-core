# -*- coding: utf-8 -*-
"""
리랭커(Reranker) 컴포넌트의 기본 인터페이스를 정의하는 모듈입니다.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any

from langchain_core.documents import Document


class BaseReranker(ABC):
    """
    리랭커(Reranker)의 기본 인터페이스를 정의하는 추상 기본 클래스(Abstract Base Class)입니다.

    리랭커는 RAG(검색 증강 생성) 파이프라인에서 중요한 역할을 합니다.
    1차적으로 벡터 유사도 검색(예: `PgVectorStore.search`)을 통해 가져온 문서들은
    의미적으로는 관련이 높지만, 때로는 사용자의 구체적인 질문 의도와는 약간의 거리가 있을 수 있습니다.

    리랭커는 이 초기 검색 결과 목록을 사용자의 원본 질문과 다시 한번 비교하여,
    질문에 가장 직접적이고 정확하게 답변할 수 있는 문서들의 순위를 더 높게 재조정합니다.
    이를 통해 최종적으로 LLM에게 전달되는 컨텍스트의 품질을 향상시켜 더 정확한 답변을 생성하도록 돕습니다.

    모든 구체적인 리랭커 클래스(예: `CohereReranker`, `NoOpReranker`)는 이 클래스를 상속받아야 합니다.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """
        현재 리랭커의 제공자(Provider)를 문자열로 반환해야 합니다.
        (예: "cohere", "cross_encoder", "none")

        Returns:
            str: 리랭커 제공자 이름.
        """
        pass

    @abstractmethod
    def rerank(
        self, query: str, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        주어진 쿼리를 기반으로 검색된 문서 목록의 순위를 재조정합니다.

        Args:
            query (str): 사용자의 원본 쿼리 텍스트.
            documents (List[Dict[str, Any]]):
                벡터 저장소에서 1차 검색된 문서 정보 딕셔너리의 리스트.
                각 딕셔너리는 'chunk_text', 'metadata', 'score' 등을 포함합니다.

        Returns:
            List[Dict[str, Any]]:
                순위가 재조정된 문서 정보 딕셔너리의 리스트.
                리스트는 새로운 점수(score) 기준으로 내림차순 정렬되어야 합니다.
        """
        pass
