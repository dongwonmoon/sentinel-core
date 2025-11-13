from typing import List
from langchain_ollama.embeddings import OllamaEmbeddings
from .base import BaseEmbeddingModel
from ..config import Settings
from ..logger import get_logger

logger = get_logger(__name__)

class OllamaEmbedding(BaseEmbeddingModel):
    """
    Ollama를 사용하여 텍스트 임베딩을 수행하는 클래스입니다.
    BaseEmbeddingModel을 상속받아 구체적인 임베딩 로직을 구현합니다.
    """

    def __init__(self, settings: Settings):
        """
        OllamaEmbedding 클래스의 인스턴스를 초기화합니다.

        Args:
            settings: 애플리케이션의 설정을 담고 있는 Settings 객체입니다.
                       Ollama 서버 URL과 모델 이름을 가져오는 데 사용됩니다.
        """
        # 설정 객체로부터 Ollama 관련 설정을 사용하여 OllamaEmbeddings 인스턴스를 생성합니다.
        self.client = OllamaEmbeddings(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_EMBEDDING_MODEL_NAME
        )
        logger.info(f"Ollama 임베딩 모델 초기화 완료. 모델: {settings.OLLAMA_EMBEDDING_MODEL_NAME}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Ollama 모델을 사용하여 여러 텍스트를 임베딩 벡터로 변환합니다.

        Args:
            texts: 임베딩할 텍스트의 리스트입니다.

        Returns:
            각 텍스트에 대한 임베딩 벡터의 리스트를 반환합니다.
        """
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        """
        Ollama 모델을 사용하여 단일 텍스트(쿼리)를 임베딩 벡터로 변환합니다.

        Args:
            text: 임베딩할 단일 텍스트입니다.

        Returns:
            주어진 텍스트에 대한 임베딩 벡터를 반환합니다.
        """
        return self.client.embed_query(text)
