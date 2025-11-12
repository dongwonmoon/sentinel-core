# tests/test_factories.py
from unittest.mock import MagicMock, patch, create_autospec

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.embeddings.base import BaseEmbeddingModel
from src.embeddings.ollama import OllamaEmbedding
from src.factories import (get_embedding_model, get_llm, get_reranker,
                           get_tools, get_vector_store)
from src.llms.base import BaseLLM
from src.llms.ollama import OllamaLLM
from src.rerankers.base import BaseReranker
from src.rerankers.noop_reranker import NoOpReranker
from src.store.base import BaseVectorStore
from src.store.milvus_vector_store import MilvusVectorStore
from src.store.pg_vector_store import PgVectorStore
from src.tools.base import BaseTool


# --- Mocking 외부 의존성 ---
# 테스트 실행 시 실제 네트워크 요청이나 파일 I/O가 발생하지 않도록
# 외부 라이브러리의 생성자를 Mocking합니다.

@pytest.fixture(autouse=True)
def mock_external_libs():
    """
    테스트 전체에서 외부 라이브러리 의존성을 자동으로 Mocking하는 Fixture.
    """
    with patch("src.embeddings.ollama.OllamaEmbeddings", MagicMock()) as mock_ollama_emb, \
         patch("src.llms.ollama.ChatOllama", MagicMock()) as mock_chat_ollama, \
         patch("src.store.pg_vector_store.create_async_engine", MagicMock()) as mock_engine, \
         patch("src.factories.CrossEncoder", MagicMock()) as mock_cross_encoder, \
         patch("src.factories.get_duckduckgo_search_tool") as mock_get_ddg_tool:
        
        # 각 Mock 객체가 spec에 정의된 인터페이스를 따르도록 설정
        mock_get_ddg_tool.return_value = create_autospec(BaseTool, instance=True)
        
        yield {
            "ollama_emb": mock_ollama_emb,
            "chat_ollama": mock_chat_ollama,
            "engine": mock_engine,
            "cross_encoder": mock_cross_encoder,
            "get_ddg_tool": mock_get_ddg_tool,
        }

# --- 팩토리 함수 테스트 ---

def test_get_embedding_model_factory():
    """get_embedding_model 팩토리 함수가 올바른 임베딩 모델 타입을 반환하는지 테스트합니다."""
    settings = Settings(EMBEDDING_MODEL_TYPE="ollama")
    model = get_embedding_model(settings)
    assert isinstance(model, OllamaEmbedding)
    assert isinstance(model, BaseEmbeddingModel)

def test_get_llm_factory():
    """get_llm 팩토리 함수가 올바른 LLM 타입을 반환하는지 테스트합니다."""
    settings = Settings(LLM_TYPE="ollama")
    llm = get_llm(settings)
    assert isinstance(llm, OllamaLLM)
    assert isinstance(llm, BaseLLM)

def test_get_vector_store_factory():
    """get_vector_store 팩토리 함수가 올바른 벡터 스토어 타입을 반환하는지 테스트합니다."""
    mock_embedding_model = MagicMock(spec=BaseEmbeddingModel)
    
    # pg_vector 테스트
    pg_settings = Settings(VECTOR_STORE_TYPE="pg_vector")
    pg_store = get_vector_store(pg_settings, mock_embedding_model)
    assert isinstance(pg_store, PgVectorStore)
    assert isinstance(pg_store, BaseVectorStore)

    # milvus 테스트 (NotImplementedError가 발생하는지 확인)
    milvus_settings = Settings(VECTOR_STORE_TYPE="milvus")
    with pytest.raises(NotImplementedError):
        get_vector_store(milvus_settings, mock_embedding_model)

def test_get_reranker_factory():
    """get_reranker 팩토리 함수가 올바른 Reranker 타입을 반환하는지 테스트합니다."""
    settings = Settings(RERANKER_TYPE="none")
    reranker = get_reranker(settings)
    assert isinstance(reranker, BaseReranker)

def test_get_tools_factory():
    """get_tools 팩토리 함수가 설정에 따라 올바른 도구 리스트를 반환하는지 테스트합니다."""
    # duckduckgo_search만 활성화된 경우
    settings_ddg = Settings(TOOLS_ENABLED=["duckduckgo_search"])
    tools_ddg = get_tools(settings_ddg)
    assert len(tools_ddg) == 1
    assert isinstance(tools_ddg[0], BaseTool)

    # 모든 도구가 비활성화된 경우
    settings_none = Settings(TOOLS_ENABLED=[])
    tools_none = get_tools(settings_none)
    assert len(tools_none) == 0

def test_unsupported_type_factories():
    """지원하지 않는 타입을 설정했을 때 각 팩토리가 ValueError를 발생시키는지 테스트합니다."""
    mock_embedding_model = MagicMock(spec=BaseEmbeddingModel)

    with pytest.raises(ValidationError):
        get_embedding_model(Settings(EMBEDDING_MODEL_TYPE="unsupported"))

    with pytest.raises(ValidationError):
        get_llm(Settings(LLM_TYPE="unsupported"))

    with pytest.raises(ValidationError):
        get_vector_store(Settings(VECTOR_STORE_TYPE="unsupported"), mock_embedding_model)
        
    with pytest.raises(ValidationError):
        get_reranker(Settings(RERANKER_TYPE="unsupported"))
