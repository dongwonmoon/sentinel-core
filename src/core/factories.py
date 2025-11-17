"""
설정(config)에 따라 각 컴포넌트의 실제 구현체를 생성하는 팩토리 함수들의 모음입니다.
이 함수들은 의존성 주입 시스템(dependencies.py)에서 사용됩니다.
"""

from typing import List, Optional

# --- 1. 설정 모델 및 컴포넌트 기반 클래스 임포트 ---
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


# --- 2. 팩토리 함수 정의 ---


def create_llm(
    llm_settings: LLMSettings,
    full_settings: Settings,  # Add full_settings here
    # 필요한 API 키는 의존성 주입 시 외부에서 전달받음
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
) -> BaseLLM:
    """설정에 맞는 LLM 인스턴스를 생성합니다."""
    if llm_settings.provider == "ollama":
        from ..components.llms.ollama import OllamaLLM

        # OLLAMA_BASE_URL 환경 변수가 설정되어 있으면 이를 우선적으로 사용
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
    # (필요 시) Anthropic 등 다른 프로바이더 추가
    # elif llm_settings.provider == "anthropic":
    #     ...
    # 새 provider가 설정에 추가되면 여기서 분기되지 않으므로 명시적으로 실패시킨다.
    raise ValueError(f"Unsupported LLM provider: {llm_settings.provider}")


def create_embedding_model(
    embedding_settings: EmbeddingSettings,
    full_settings: Optional[Settings] = None,
    openai_api_key: Optional[str] = None,
) -> BaseEmbeddingModel:
    """설정에 맞는 임베딩 모델 인스턴스를 생성합니다."""
    if embedding_settings.provider == "ollama":
        from ..components.embeddings.ollama import OllamaEmbedding
        import logging

        logger = logging.getLogger("embedding.debug")

        logger.warning(
            f"[DEBUG] EMBEDDING SETTINGS api_base={embedding_settings.api_base}"
        )
        logger.warning(
            f"[DEBUG] OLLAMA_BASE_URL from Settings={getattr(full_settings,'OLLAMA_BASE_URL', None)}"
        )

        base_url = None
        if getattr(embedding_settings, "api_base", None):
            base_url = embedding_settings.api_base
        elif full_settings and getattr(full_settings, "OLLAMA_BASE_URL", None):
            base_url = full_settings.OLLAMA_BASE_URL

        logger.warning(f"[DEBUG] FINAL base_url USED FOR EMBEDDING = {base_url}")

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
    # (필요 시) HuggingFace 등 다른 프로바이더 추가
    # elif embedding_settings.provider == "huggingface":
    #     ...
    # 지원하지 않는 provider는 환경 설정이 잘못된 것이므로 빠르게 예외를 던진다.
    raise ValueError(f"Unsupported embedding provider: {embedding_settings.provider}")


def create_vector_store(
    vs_settings: VectorStoreSettings,
    # DB 연결 정보 등 전체 설정이 필요할 수 있음
    full_settings: Settings,
    embedding_model: BaseEmbeddingModel,
) -> BaseVectorStore:
    """설정에 맞는 벡터 스토어 인스턴스를 생성합니다."""
    if vs_settings.provider == "pg_vector":
        from ..components.vector_stores.pg_vector_store import PgVectorStore

        return PgVectorStore(settings=full_settings, embedding_model=embedding_model)
    if vs_settings.provider == "milvus":
        from ..components.vector_stores.milvus_vector_store import (
            MilvusVectorStore,
        )

        return MilvusVectorStore(
            settings=full_settings, embedding_model=embedding_model
        )
    # 설정 검증이 통과했는데도 이 지점에 오면 잘못된 provider가 입력된 것이므로 즉시 오류를 낸다.
    raise ValueError(f"Unsupported vector store provider: {vs_settings.provider}")


def create_reranker(
    reranker_settings: RerankerSettings,
    cohere_api_key: Optional[str] = None,
) -> BaseReranker:
    """설정에 맞는 Reranker 인스턴스를 생성합니다."""
    if reranker_settings.provider == "none":
        from ..components.rerankers.noop_reranker import NoOpReranker

        return NoOpReranker()
    if reranker_settings.provider == "cross_encoder":
        # 이 방식은 모델을 직접 다운로드하므로 API 키가 필요 없음
        from sentence_transformers import CrossEncoder

        return CrossEncoder(reranker_settings.model_name, max_length=512)
    # (필요 시) Cohere 등 다른 프로바이더 추가
    # elif reranker_settings.provider == "cohere":
    #     ...
    raise ValueError(f"Unsupported reranker provider: {reranker_settings.provider}")


def get_tools(enabled_tools_config: List[str]) -> List[BaseTool]:
    """설정에 따라 활성화된 도구 목록을 생성합니다."""
    enabled_tools = []
    # settings.tools_enabled 에 정의된 식별자만 로딩하여 불필요한 의존성 초기화를 막는다.
    if "duckduckgo_search" in enabled_tools_config:
        from ..components.tools.duckduckgo_search import (
            get_duckduckgo_search_tool,
        )

        enabled_tools.append(get_duckduckgo_search_tool())

    if "code_execution" in enabled_tools_config:
        from ..components.tools.code_execution import get_code_execution_tool

        enabled_tools.append(get_code_execution_tool())

    # (필요 시) Google Search 등 다른 도구 추가
    # if "google_search" in enabled_tools_config:
    #     ...

    return enabled_tools
