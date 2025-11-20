"""
애플리케이션의 핵심 컴포넌트(LLM, 임베딩 모델 등)를 생성하는 팩토리 모듈.

이 모듈의 함수들은 설정(settings) 객체를 입력으로 받아, 해당 설정에 맞는
구체적인 컴포넌트의 인스턴스를 동적으로 생성하고 반환합니다.

이를 통해 컴포넌트의 실제 구현을 사용하는 코드(예: Orchestrator)로부터 분리하여
유연하고 확장 가능한 구조를 만듭니다.
"""
from typing import List

from ..components.embeddings.base import BaseEmbeddingModel
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.tools.base import BaseTool
from ..components.vector_stores.base import BaseVectorStore
from .config import Settings


def create_llm(settings: Settings) -> BaseLLM:
    """설정에 따라 LLM 컴포넌트 인스턴스를 생성합니다."""
    llm_conf = settings.llm

    if llm_conf.provider == "ollama":
        from ..components.llms.ollama import OllamaLLM

        ollama_base_url = settings.OLLAMA_BASE_URL or llm_conf.api_base
        if not ollama_base_url:
            raise ValueError("Ollama API base URL is not configured.")
        return OllamaLLM(
            base_url=ollama_base_url,
            model_name=llm_conf.model_name,
            temperature=llm_conf.temperature,
        )
    elif llm_conf.provider == "openai":
        from ..components.llms.openai import OpenAILLM

        api_key = settings.OPENAI_API_KEY
        return OpenAILLM(
            base_url=llm_conf.api_base,
            model_name=llm_conf.model_name,
            api_key=api_key,
            temperature=llm_conf.temperature,
        )
    raise ValueError(f"Unsupported LLM provider: {llm_conf.provider}")


def create_embedding_model(settings: Settings) -> BaseEmbeddingModel:
    """설정에 따라 임베딩 모델 인스턴스를 생성합니다."""
    emb_conf = settings.embedding
    if emb_conf.provider == "ollama":
        from ..components.embeddings.ollama import OllamaEmbedding

        base_url = None
        if getattr(emb_conf, "api_base", None):
            base_url = emb_conf.api_base
        elif settings and getattr(settings, "OLLAMA_BASE_URL", None):
            base_url = settings.OLLAMA_BASE_URL
        return OllamaEmbedding(model_name=emb_conf.model_name, base_url=base_url)
    elif emb_conf.provider == "openai":
        from ..components.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model_name=emb_conf.model_name,
            api_key=settings.OPENAI_API_KEY,
            base_url=getattr(emb_conf, "api_base", None),
        )
    raise ValueError(f"Unsupported embedding provider: {emb_conf.provider}")


def create_vector_store(
    settings: Settings, embedding_model: BaseEmbeddingModel
) -> BaseVectorStore:
    """설정에 따라 벡터 저장소 인스턴스를 생성합니다."""
    vs_conf = settings.vector_store
    if vs_conf.provider == "pg_vector":
        from ..components.vector_stores.pg_vector_store import PgVectorStore

        return PgVectorStore(settings=settings, embedding_model=embedding_model)
    raise ValueError(f"Unsupported vector store provider: {vs_conf.provider}")


def create_reranker(
    settings: Settings,
) -> BaseReranker:
    """설정에 따라 리랭커 인스턴스를 생성합니다."""
    reranker_conf = settings.reranker
    if reranker_conf.provider == "none":
        from ..components.rerankers.noop_reranker import NoOpReranker

        return NoOpReranker()
    if reranker_conf.provider == "cross_encoder":
        from sentence_transformers import CrossEncoder

        return CrossEncoder(reranker_conf.model_name, max_length=512)
    raise ValueError(f"Unsupported reranker provider: {reranker_conf.provider}")


def get_tools(enabled_tools_config: List[str]) -> List[BaseTool]:
    """활성화된 도구 설정에 따라 도구 인스턴스 리스트를 반환합니다.

    Args:
        enabled_tools_config (List[str]): 활성화할 도구의 이름 리스트.

    Returns:
        List[BaseTool]: 생성된 도구 인스턴스의 리스트.
    """
    # TODO: 설정에 따라 실제 도구(예: DuckDuckGo 검색)를 생성하는 로직 구현 필요.
    return []
