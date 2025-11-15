# -*- coding: utf-8 -*-
"""
리랭킹(Re-ranking)을 수행하지 않는 'No-Operation' 리랭커 구현체입니다.
"""

from typing import List, Dict, Any

from .base import BaseReranker
from ...core.logger import get_logger

logger = get_logger(__name__)


class NoOpReranker(BaseReranker):
    """
    아무 작업도 수행하지 않는 리랭커(Reranker) 구현체입니다.

    이 클래스는 `config.yml` 등에서 리랭커 기능이 비활성화(`provider: "none"`)되었을 때
    사용되는 기본 폴백(fallback) 메커니즘입니다.

    RAG 파이프라인의 리랭킹 단계를 효과적으로 건너뛰게 해주며,
    리랭커의 존재 여부와 관계없이 파이프라인의 전체 구조를 일관되게 유지할 수 있도록 돕습니다.
    """

    def __init__(self):
        self._provider = "none"
        logger.info(
            "NoOpReranker가 초기화되었습니다. 리랭킹 단계를 건너뜁니다."
        )

    @property
    def provider(self) -> str:
        """
        리랭커 제공자 이름("none")을 반환합니다.
        """
        return self._provider

    def rerank(
        self, query: str, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        입력받은 문서 목록을 아무런 수정 없이 그대로 반환합니다.

        Args:
            query (str): 사용자의 원본 쿼리 텍스트 (이 클래스에서는 사용되지 않음).
            documents (List[Dict[str, Any]]):
                벡터 저장소에서 1차 검색된 문서 정보 딕셔너리의 리스트.

        Returns:
            List[Dict[str, Any]]: 입력받은 것과 동일한 문서 정보 딕셔너리의 리스트.
        """
        logger.debug(
            f"NoOpReranker가 호출되었습니다. {len(documents)}개의 문서 순위를 재조정하지 않고 그대로 반환합니다."
        )
        return documents
