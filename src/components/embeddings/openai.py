from typing import List
from langchain_openai import OpenAIEmbeddings
from .base import BaseEmbeddingModel
from ...core.config import Settings


class OpenAIEmbedding(BaseEmbeddingModel):
    """
    OpenAI 호환 API를 사용하여 텍스트 임베딩을 수행하는 클래스입니다.
    """

    def __init__(self, model_name: str, api_key: str, base_url: str = None):
        self.client = OpenAIEmbeddings(
            base_url=base_url,
            api_key=api_key,
            model=model_name,
        )
        print(f"INFO: OpenAI/Groq 임베딩 모델 초기화 완료. 모델: {model_name}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self.client.embed_documents(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.client.embed_query(text)
