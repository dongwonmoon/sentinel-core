from typing import List, Tuple
from langchain_core.documents import Document
from .base import BaseReranker
from ..logger import get_logger

logger = get_logger(__name__)


class NoOpReranker(BaseReranker):
    """
    아무 작업도 수행하지 않는 Reranker 구현체입니다.
    Reranker를 사용하지 않을 때 기본으로 사용됩니다.
    """

    def rerank(
        self,
        query: str,
        documents: List[Tuple[Document, float]],
    ) -> List[Tuple[Document, float]]:
        """
        입력받은 문서 목록을 수정 없이 그대로 반환합니다.

        Args:
            query: 사용자의 원본 쿼리 텍스트입니다.
            documents: (Document, 초기 점수) 튜플의 리스트입니다.

        Returns:
            입력받은 것과 동일한 (Document, 점수) 튜플의 리스트를 반환합니다.
        """
        logger.info("NoOpReranker 사용. 순위 재조정을 건너뜁니다.")
        return documents
