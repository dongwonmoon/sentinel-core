from typing import List
from langchain_openai import OpenAIEmbeddings
from .base import BaseEmbeddingModel
from src.config import Settings


class OpenAIEmbedding(BaseEmbeddingModel):
    """
    OpenAI 호환 API를 사용하여 텍스트 임베딩을 수행하는 클래스입니다.
    """

    def __init__(self, settings: Settings):
        self.client = OpenAIEmbeddings(
            base_url=settings.OPENAI_API_BASE_URL,
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_EMBEDDING_MODEL_NAME,
        )
        print(
            f"INFO: OpenAI/Groq 임베딩 모델 초기화 완료. 모델: {settings.OPENAI_EMBEDDING_MODEL_NAME}"
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.client.embed_query(text)
