# -*- coding: utf-8 -*-
"""
임베딩 모델 컴포넌트의 기본 인터페이스를 정의하는 모듈입니다.
"""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingModel(ABC):
    """
    텍스트 임베딩 모델의 기본 인터페이스를 정의하는 추상 기본 클래스(Abstract Base Class)입니다.

    이 클래스는 시스템 내에서 사용되는 모든 구체적인 임베딩 모델 클래스(예: `OllamaEmbedding`, `OpenAIEmbedding`)들이
    반드시 구현해야 하는 공통 메서드를 강제합니다. 이를 통해, 어떤 임베딩 모델을 사용하든
    동일한 방식으로 텍스트를 벡터로 변환할 수 있어 모델 교체의 유연성을 확보하고 코드의 일관성을 유지합니다.
    """

    @property
    @abstractmethod
    def provider(self) -> str:
        """
        현재 임베딩 모델의 제공자(Provider)를 문자열로 반환해야 합니다.
        (예: "ollama", "openai", "huggingface")

        Returns:
            str: 임베딩 모델 제공자 이름.
        """
        pass

    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        여러 개의 텍스트(문서)를 한 번에 임베딩(Embedding)합니다.

        이 메서드는 데이터베이스에 저장할 여러 문서 청크(chunk)들을 배치(batch) 처리하여
        벡터로 변환할 때 주로 사용됩니다. 여러 텍스트를 한 번에 처리함으로써
        네트워크 오버헤드를 줄이고 처리 효율을 높일 수 있습니다.

        Args:
            texts (List[str]): 임베딩할 텍스트(문서)의 리스트.

        Returns:
            List[List[float]]: 각 텍스트에 대한 임베딩 벡터의 리스트.
                               (예: [[0.1, 0.2, ...], [0.4, 0.5, ...]])
        """
        pass

    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        단일 텍스트(주로 사용자 쿼리)를 임베딩합니다.

        이 메서드는 사용자의 질문이나 검색어와 같이 단일 텍스트를 벡터로 변환하여
        벡터 데이터베이스에서 유사한 문서를 찾는 데 사용됩니다.

        Args:
            text (str): 임베딩할 단일 텍스트(쿼리).

        Returns:
            List[float]: 주어진 텍스트에 대한 임베딩 벡터. (예: [0.1, 0.2, ...])
        """
        pass
