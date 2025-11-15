# -*- coding: utf-8 -*-
"""
OpenAI의 임베딩 모델을 사용하기 위한 구체적인 구현체입니다.
"""

from typing import List, Optional

from langchain_openai import OpenAIEmbeddings as LangchainOpenAIEmbeddings

from .base import BaseEmbeddingModel
from ...core.logger import get_logger

logger = get_logger(__name__)


class OpenAIEmbedding(BaseEmbeddingModel):
    """
    OpenAI API를 사용하여 텍스트 임베딩을 수행하는 클래스입니다.

    `BaseEmbeddingModel` 추상 클래스를 상속받아, `langchain-openai`의 `OpenAIEmbeddings`를 사용하여
    문서 및 쿼리 임베딩 로직을 구체적으로 구현합니다.
    """

    def __init__(
        self, model_name: str, api_key: Optional[str], base_url: Optional[str] = None
    ):
        """
        OpenAIEmbedding 클래스의 인스턴스를 초기화합니다.

        Args:
            model_name (str): 사용할 OpenAI 임베딩 모델의 이름 (예: "text-embedding-3-small").
            api_key (Optional[str]): OpenAI API 인증을 위한 API 키.
            base_url (Optional[str]): OpenAI 호환 API 엔드포인트의 기본 URL.
                                      (이 프로젝트에서는 주로 사용되지 않음)
        """
        self._provider = "openai"
        self._model_name = model_name

        logger.info(f"OpenAI 임베딩 모델 ('{model_name}') 초기화를 시작합니다.")

        if not api_key:
            logger.warning(
                f"'{model_name}' 모델에 대한 API 키가 제공되지 않았습니다. "
                "환경 변수(OPENAI_API_KEY)에 설정되어 있는지 확인하세요."
            )

        try:
            # langchain-openai의 OpenAIEmbeddings 클라이언트를 초기화합니다.
            self.client = LangchainOpenAIEmbeddings(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
            )
            logger.info(f"OpenAI 임베딩 모델 ('{model_name}') 초기화가 완료되었습니다.")
        except Exception as e:
            logger.error(
                f"OpenAI 임베딩 모델 ('{model_name}') 초기화 중 오류 발생: {e}",
                exc_info=True,
            )
            raise

    @property
    def provider(self) -> str:
        """
        임베딩 모델 제공자 이름("openai")을 반환합니다.
        """
        return self._provider

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        OpenAI 모델을 사용하여 여러 텍스트(문서)를 임베딩 벡터로 변환합니다.
        실제 로직은 `OpenAIEmbeddings`의 `embed_documents` 메서드에 위임합니다.

        Args:
            texts (List[str]): 임베딩할 텍스트의 리스트.

        Returns:
            List[List[float]]: 각 텍스트에 대한 임베딩 벡터의 리스트.
        """
        logger.debug(f"'{self._model_name}' 모델로 {len(texts)}개 문서의 임베딩을 시작합니다.")
        try:
            embeddings = self.client.embed_documents(texts)
            logger.debug(f"{len(texts)}개 문서의 임베딩을 성공적으로 완료했습니다.")
            return embeddings
        except Exception as e:
            logger.error(
                f"'{self._model_name}' 모델로 문서 임베딩 중 오류 발생: {e}",
                exc_info=True,
            )
            raise

    def embed_query(self, text: str) -> List[float]:
        """
        OpenAI 모델을 사용하여 단일 텍스트(쿼리)를 임베딩 벡터로 변환합니다.
        실제 로직은 `OpenAIEmbeddings`의 `embed_query` 메서드에 위임합니다.

        Args:
            text (str): 임베딩할 단일 텍스트.

        Returns:
            List[float]: 주어진 텍스트에 대한 임베딩 벡터.
        """
        logger.debug(f"'{self._model_name}' 모델로 쿼리 임베딩을 시작합니다: '{text[:80]}...'")
        try:
            embedding = self.client.embed_query(text)
            logger.debug("쿼리 임베딩을 성공적으로 완료했습니다.")
            return embedding
        except Exception as e:
            logger.error(
                f"'{self._model_name}' 모델로 쿼리 임베딩 중 오류 발생: {e}",
                exc_info=True,
            )
            raise
