from typing import List, Optional
from .config import (
    Settings,
    LLMSettings,
    EmbeddingSettings,
    VectorStoreSettings,
    RerankerSettings,
)
from ..components.embeddings.base import BaseEmbeddingModel
from ..components.llms.base import BaseLLM
from ..components.rerankers.base import BaseReranker
from ..components.vector_stores.base import BaseVectorStore
from ..components.tools.base import BaseTool


def create_llm(
    llm_settings: LLMSettings,
    full_settings: Settings,
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
) -> BaseLLM:
    if llm_settings.provider == "ollama":
        from ..components.llms.ollama import OllamaLLM

        ollama_base_url = full_settings.OLLAMA_BASE_URL or llm_settings.api_base
        if not ollama_base_url:
            raise ValueError("Ollama API base URL is not configured.")
        return OllamaLLM(
            base_url=ollama_base_url,
            model_name=llm_settings.model_name,
            temperature=llm_settings.temperature,
        )
    elif llm_settings.provider == "openai":
        from ..components.llms.openai import OpenAILLM

        return OpenAILLM(
            base_url=llm_settings.api_base,
            model_name=llm_settings.model_name,
            api_key=openai_api_key,
            temperature=llm_settings.temperature,
        )
    raise ValueError(f"Unsupported LLM provider: {llm_settings.provider}")


def create_embedding_model(
    embedding_settings: EmbeddingSettings,
    full_settings: Optional[Settings] = None,
    openai_api_key: Optional[str] = None,
) -> BaseEmbeddingModel:
    if embedding_settings.provider == "ollama":
        from ..components.embeddings.ollama import OllamaEmbedding

        base_url = None
        if getattr(embedding_settings, "api_base", None):
            base_url = embedding_settings.api_base
        elif full_settings and getattr(full_settings, "OLLAMA_BASE_URL", None):
            base_url = full_settings.OLLAMA_BASE_URL
        return OllamaEmbedding(
            model_name=embedding_settings.model_name, base_url=base_url
        )
    elif embedding_settings.provider == "openai":
        from ..components.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model_name=embedding_settings.model_name,
            api_key=openai_api_key,
            base_url=getattr(embedding_settings, "api_base", None),
        )
    raise ValueError(
        f"Unsupported embedding provider: {embedding_settings.provider}"
    )


def create_vector_store(
    vs_settings: VectorStoreSettings,
    full_settings: Settings,
    embedding_model: BaseEmbeddingModel,
) -> BaseVectorStore:
    if vs_settings.provider == "pg_vector":
        from ..components.vector_stores.pg_vector_store import PgVectorStore

        return PgVectorStore(
            settings=full_settings, embedding_model=embedding_model
        )
    raise ValueError(
        f"Unsupported vector store provider: {vs_settings.provider}"
    )


def create_reranker(
    reranker_settings: RerankerSettings,
    cohere_api_key: Optional[str] = None,
) -> BaseReranker:
    if reranker_settings.provider == "none":
        from ..components.rerankers.noop_reranker import NoOpReranker

        return NoOpReranker()
    if reranker_settings.provider == "cross_encoder":
        from sentence_transformers import CrossEncoder

        return CrossEncoder(reranker_settings.model_name, max_length=512)
    raise ValueError(
        f"Unsupported reranker provider: {reranker_settings.provider}"
    )


def get_tools(enabled_tools_config: List[str]) -> List[BaseTool]:
    """
    [MVP] 현재는 외부 도구를 사용하지 않으므로 빈 리스트를 반환합니다.
    """
    return []
