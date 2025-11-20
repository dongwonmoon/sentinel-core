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


def create_llm(settings: Settings) -> BaseLLM:
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
    emb_conf = settings.embedding
    if emb_conf.provider == "ollama":
        from ..components.embeddings.ollama import OllamaEmbedding

        base_url = None
        if getattr(emb_conf, "api_base", None):
            base_url = emb_conf.api_base
        elif settings and getattr(settings, "OLLAMA_BASE_URL", None):
            base_url = settings.OLLAMA_BASE_URL
        return OllamaEmbedding(
            model_name=emb_conf.model_name, base_url=base_url
        )
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
    vs_conf = settings.vector_store
    if vs_conf.provider == "pg_vector":
        from ..components.vector_stores.pg_vector_store import PgVectorStore

        return PgVectorStore(settings=settings, embedding_model=embedding_model)
    raise ValueError(f"Unsupported vector store provider: {vs_conf.provider}")


def create_reranker(
    settings: Settings,
) -> BaseReranker:
    reranker_conf = settings.reranker
    if reranker_conf.provider == "none":
        from ..components.rerankers.noop_reranker import NoOpReranker

        return NoOpReranker()
    if reranker_conf.provider == "cross_encoder":
        from sentence_transformers import CrossEncoder

        return CrossEncoder(reranker_conf.model_name, max_length=512)
    raise ValueError(f"Unsupported reranker provider: {reranker_conf.provider}")


def get_tools(enabled_tools_config: List[str]) -> List[BaseTool]:
    """
    [MVP] 현재는 외부 도구를 사용하지 않으므로 빈 리스트를 반환합니다.
    """
    return []
