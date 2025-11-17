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
    full_settings: Settings,
    # 필요한 API 키는 의존성 주입 시 외부에서 전달받음
    openai_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
) -> BaseLLM:
    """설정에 맞는 LLM 인스턴스를 생성합니다."""
    if llm_settings.provider == "ollama":
        from ..components.llms.ollama import OllamaLLM

        # OLLAMA_BASE_URL 환경 변수(전역 설정)가 있으면 이를 우선적으로 사용하고,
        # 없으면 llm_settings(개별 LLM 설정)에 정의된 api_base를 사용합니다.
        # 이를 통해 개발 환경에서는 로컬 Ollama를, 프로덕션에서는 중앙 서버를 쉽게 지정할 수 있습니다.
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
    # 설정 파일(config.yml)의 유효성 검사는 Pydantic 모델에서 이미 수행되었으므로,
    # 이 지점에 도달했다는 것은 지원하지 않는 provider가 설정에 포함되었음을 의미합니다.
    # 따라서 명시적인 ValueError를 발생시켜 문제를 빠르게 파악하도록 합니다.
    raise ValueError(f"Unsupported LLM provider: {llm_settings.provider}")


def create_embedding_model(
    embedding_settings: EmbeddingSettings,
    full_settings: Optional[Settings] = None,
    openai_api_key: Optional[str] = None,
) -> BaseEmbeddingModel:
    """설정에 맞는 임베딩 모델 인스턴스를 생성합니다."""
    if embedding_settings.provider == "ollama":
        from ..components.embeddings.ollama import OllamaEmbedding

        # LLM 팩토리와 유사하게, 전역 OLLAMA_BASE_URL 또는 개별 설정을 사용합니다.
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
    # (필요 시) HuggingFace 등 다른 프로바이더 추가
    # elif embedding_settings.provider == "huggingface":
    #     ...
    raise ValueError(
        f"Unsupported embedding provider: {embedding_settings.provider}"
    )


def create_vector_store(
    vs_settings: VectorStoreSettings,
    # DB 연결 정보 등 전체 설정이 필요할 수 있으므로 full_settings를 받습니다.
    full_settings: Settings,
    embedding_model: BaseEmbeddingModel,
) -> BaseVectorStore:
    """설정에 맞는 벡터 스토어 인스턴스를 생성합니다."""
    if vs_settings.provider == "pg_vector":
        from ..components.vector_stores.pg_vector_store import PgVectorStore

        # PgVectorStore는 DB 연결을 위해 전체 설정 객체(DATABASE_URL 포함)를 필요로 합니다.
        return PgVectorStore(
            settings=full_settings, embedding_model=embedding_model
        )
    if vs_settings.provider == "milvus":
        from ..components.vector_stores.milvus_vector_store import (
            MilvusVectorStore,
        )

        return MilvusVectorStore(
            settings=full_settings, embedding_model=embedding_model
        )
    raise ValueError(
        f"Unsupported vector store provider: {vs_settings.provider}"
    )


def create_reranker(
    reranker_settings: RerankerSettings,
    cohere_api_key: Optional[str] = None,
) -> BaseReranker:
    """설정에 맞는 Reranker 인스턴스를 생성합니다."""
    if reranker_settings.provider == "none":
        from ..components.rerankers.noop_reranker import NoOpReranker

        # 'none' 프로바이더는 아무 작업도 하지 않는 NoOpReranker를 반환합니다.
        # 이는 리랭커를 사용하고 싶지 않을 때 유용합니다.
        return NoOpReranker()
    if reranker_settings.provider == "cross_encoder":
        # sentence-transformers 라이브러리를 사용하여 로컬에서 실행되는 CrossEncoder 모델을 로드합니다.
        # 이 방식은 별도의 API 키가 필요 없는 장점이 있습니다.
        from sentence_transformers import CrossEncoder

        return CrossEncoder(reranker_settings.model_name, max_length=512)
    # (필요 시) Cohere 등 다른 프로바이더 추가
    # elif reranker_settings.provider == "cohere":
    #     ...
    raise ValueError(
        f"Unsupported reranker provider: {reranker_settings.provider}"
    )


def get_tools(enabled_tools_config: List[str]) -> List[BaseTool]:
    """
    설정에 따라 활성화된 도구 목록을 생성합니다.
    이러한 동적 로딩 방식은 필요한 도구만 초기화하여 메모리 사용량을 줄이고
    애플리케이션 시작 시간을 단축하는 데 도움이 됩니다.
    """
    enabled_tools = []
    # settings.tools_enabled에 정의된 식별자만 로딩하여 불필요한 의존성 초기화를 막습니다.
    if "duckduckgo_search" in enabled_tools_config:
        from ..components.tools.duckduckgo_search import (
            get_duckduckgo_search_tool,
        )

        enabled_tools.append(get_duckduckgo_search_tool())

    if "code_execution" in enabled_tools_config:
        from ..components.tools.code_execution import get_code_execution_tool

        enabled_tools.append(get_code_execution_tool())

    # (필요 시) Google Search 등 다른 도구를 여기에 추가할 수 있습니다.
    # if "google_search" in enabled_tools_config:
    #     ...

    return enabled_tools
