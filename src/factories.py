from typing import List

from .config import Settings
from .embeddings.base import BaseEmbeddingModel
from .embeddings.ollama import OllamaEmbedding
from .embeddings.openai import OpenAIEmbedding
from .llms.base import BaseLLM
from .llms.ollama import OllamaLLM
from .llms.openai import OpenAILLM
from .rerankers.base import BaseReranker
from .rerankers.noop_reranker import NoOpReranker
from .store.base import BaseVectorStore
from .store.pg_vector_store import PgVectorStore
from .store.milvus_vector_store import MilvusVectorStore
from .tools.base import BaseTool
from .tools.duckduckgo_search import get_duckduckgo_search_tool
from .tools.code_execution import get_code_execution_tool

# 설정(settings)에 따라 실제 구현체를 동적으로 생성하는 함수들입니다.


def get_embedding_model(s: Settings) -> BaseEmbeddingModel:
    """설정에 맞는 임베딩 모델 인스턴스를 생성합니다."""
    if s.EMBEDDING_MODEL_TYPE == "ollama":
        return OllamaEmbedding(settings=s)
    elif s.EMBEDDING_MODEL_TYPE == "openai":
        return OpenAIEmbedding(settings=s)
    raise ValueError(
        f"Unsupported embedding model type: {s.EMBEDDING_MODEL_TYPE}"
    )


def get_llm(s: Settings) -> BaseLLM:
    """설정에 맞는 LLM 인스턴스를 생성합니다."""
    if s.LLM_TYPE == "ollama":
        return OllamaLLM(settings=s)
    elif s.LLM_TYPE == "openai":
        return OpenAILLM(settings=s)
    raise ValueError(f"Unsupported LLM type: {s.LLM_TYPE}")


def get_vector_store(
    s: Settings, embedding_model: BaseEmbeddingModel
) -> BaseVectorStore:
    """설정에 맞는 벡터 스토어 인스턴스를 생성합니다."""
    if s.VECTOR_STORE_TYPE == "pg_vector":
        return PgVectorStore(settings=s, embedding_model=embedding_model)
    if s.VECTOR_STORE_TYPE == "milvus":
        return MilvusVectorStore(settings=s, embedding_model=embedding_model)
    raise ValueError(f"Unsupported vector store type: {s.VECTOR_STORE_TYPE}")


def get_reranker(s: Settings) -> BaseReranker:
    """설정에 맞는 Reranker 인스턴스를 생성합니다."""
    if s.RERANKER_TYPE == "none":
        return NoOpReranker()
    if s.RERANKER_TYPE == "cross_encoder":
        from sentence_transformers import CrossEncoder

        return CrossEncoder(s.CROSS_ENCODER_MODEL_NAME, max_length=512)
    raise ValueError(f"Unsupported reranker type: {s.RERANKER_TYPE}")


def get_tools(s: Settings) -> List[BaseTool]:
    """설정에 따라 활성화된 도구 목록을 생성합니다."""
    enabled_tools = []
    if "duckduckgo_search" in s.TOOLS_ENABLED:
        enabled_tools.append(get_duckduckgo_search_tool())

    if "code_execution" in s.TOOLS_ENABLED:
        enabled_tools.append(get_code_execution_tool())

    return enabled_tools
