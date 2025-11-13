from abc import ABC, abstractmethod
from typing import List

class BaseEmbeddingModel(ABC):
    """
    임베딩 모델의 기본 인터페이스를 정의하는 추상 기본 클래스(ABC)입니다.
    모든 구체적인 임베딩 모델 클래스는 이 클래스를 상속받아야 합니다.
    """

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        여러 개의 텍스트(문서)를 한 번에 임베딩합니다.

        Args:
            texts: 임베딩할 텍스트의 리스트입니다.

        Returns:
            각 텍스트에 대한 임베딩 벡터의 리스트를 반환합니다.
        """
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        단일 텍스트(쿼리)를 임베딩합니다.

        Args:
            text: 임베딩할 단일 텍스트입니다.

        Returns:
            주어진 텍스트에 대한 임베딩 벡터를 반환합니다.
        """
        pass
