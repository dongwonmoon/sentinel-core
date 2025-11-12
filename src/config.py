from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple, Type

import yaml
from pydantic_settings import (BaseSettings, PydanticBaseSettingsSource,
                               SettingsConfigDict)

# 1. YAML 설정 소스 함수 정의
def yaml_config_settings_source(settings: BaseSettings) -> dict[str, Any]:
    """
    프로젝트 루트의 'config.yml' 파일을 읽어 Pydantic 설정 소스로 사용합니다.
    """
    config_path = Path(__file__).parent.parent / "config.yml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

# 2. Settings 클래스 수정
class Settings(BaseSettings):
    """
    애플리케이션의 모든 설정을 관리하는 Pydantic BaseSettings 클래스입니다.
    YAML, 환경 변수, 기본값 순서로 설정을 로드합니다.
    """
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/sentinel"
    VECTOR_STORE_TYPE: Literal["pg_vector", "milvus"] = "pg_vector"
    MILVUS_HOST: Optional[str] = None
    MILVUS_PORT: Optional[int] = None
    LLM_TYPE: Literal["ollama", "openai", "anthropic"] = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_NAME: str = "llama3"
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL_NAME: str = "gpt-4o"
    ANTHROPIC_API_KEY: Optional[str] = None
    ANTHROPIC_MODEL_NAME: str = "claude-3-opus-20240229"
    EMBEDDING_MODEL_TYPE: Literal["ollama", "huggingface", "openai"] = "ollama"
    OLLAMA_EMBEDDING_MODEL_NAME: str = "llama3"
    HUGGINGFACE_EMBEDDING_MODEL_NAME: Optional[str] = "sentence-transformers/all-MiniLM-L6-v2"
    OPENAI_EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"
    RERANKER_TYPE: Literal["none", "cohere", "cross_encoder"] = "none"
    COHERE_API_KEY: Optional[str] = None
    CROSS_ENCODER_MODEL_NAME: Optional[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    TOOLS_ENABLED: List[Literal["duckduckgo_search", "google_search", "code_execution"]] = ["duckduckgo_search"]
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    APP_TITLE: str = "Sentinel RAG System"
    APP_DESCRIPTION: str = "Enterprise-grade RAG system with advanced capabilities."
    LOG_LEVEL: str = "INFO"

    # 3. 커스텀 설정 소스 지정
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Pydantic이 설정을 읽어오는 소스의 순서를 재정의합니다.
        1. init_settings: Settings() 호출 시 직접 전달된 인자
        2. env_settings: 환경 변수
        3. dotenv_settings: .env 파일
        4. yaml_config_settings_source: config.yml 파일
        5. file_secret_settings: Docker secrets 등 파일 기반 시크릿
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_config_settings_source,
            file_secret_settings,
        )

# Settings 인스턴스를 생성하여 애플리케이션 전반에서 사용합니다.
settings = Settings()
