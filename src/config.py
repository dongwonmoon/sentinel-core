from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple, Type
import yaml
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from pydantic import computed_field, Field


def yaml_config_settings_source() -> dict[str, Any]:
    """
    프로젝트 루트의 'config.yml' 파일을 읽어 Pydantic 설정 소스로 사용합니다.
    """
    config_path = Path(__file__).parent.parent / "config.yml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Settings(BaseSettings):
    """
    애플리케이션의 모든 설정을 관리하는 Pydantic BaseSettings 클래스입니다.
    YAML, 환경 변수(.env), 기본값 순서로 설정을 로드합니다.
    """

    # --- 환경 변수(.env)로만 관리되어야 하는 민감 정보 ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    # Redis 연결 정보
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # JWT 인증을 위한 비밀 키
    AUTH_SECRET_KEY: str

    # API 키
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # --- config.yml 또는 기본값으로 관리되는 일반 설정 ---
    # 애플리케이션 정보
    APP_TITLE: str = "Sentinel RAG System"
    APP_DESCRIPTION: str = "Enterprise-grade RAG system with advanced capabilities."
    LOG_LEVEL: str = "INFO"

    # 벡터 스토어 설정
    VECTOR_STORE_TYPE: Literal["pg_vector", "milvus"] = "pg_vector"
    MILVUS_HOST: Optional[str] = None
    MILVUS_PORT: Optional[int] = None

    # LLM 설정
    LLM_TYPE: Literal["ollama", "openai", "anthropic"] = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_NAME: str = "llama3"
    OLLAMA_TEMPERATURE: float = 0

    OPENAI_API_BASE_URL: Optional[str] = "https://api.groq.com/openai/v1"
    OPENAI_MODEL_NAME: str = "llama3-8b-8192"

    ANTHROPIC_MODEL_NAME: str = "claude-3-opus-20240229"

    POWERFUL_LLM_TYPE: Literal["ollama", "openai", "anthropic"] = "ollama"
    POWERFUL_API_BASE_URL: Optional[str] = "http://localhost:11435"  # (예: RunPod URL)
    POWERFUL_MODEL_NAME: Optional[str] = "llama3:70b"
    POWERFUL_LLM_TEMPERATURE: float = 0

    # 임베딩 모델 설정
    EMBEDDING_MODEL_TYPE: Literal["ollama", "huggingface", "openai"] = "ollama"
    OLLAMA_EMBEDDING_MODEL_NAME: str = "nomic-embed-text"
    HUGGINGFACE_EMBEDDING_MODEL_NAME: Optional[str] = (
        "sentence-transformers/all-MiniLM-L6-v2"
    )
    OPENAI_EMBEDDING_MODEL_NAME: str = "text-embedding-3-small"

    # Reranker 설정
    RERANKER_TYPE: Literal["none", "cohere", "cross_encoder"] = "none"
    CROSS_ENCODER_MODEL_NAME: Optional[str] = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # 도구 설정
    TOOLS_ENABLED: List[
        Literal["duckduckgo_search", "google_search", "code_execution"]
    ] = ["duckduckgo_search"]

    # JWT 인증 설정
    AUTH_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # --- 동적으로 계산되는 필드 ---
    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy 비동기(asyncpg) URL을 생성합니다."""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Alembic을 위한 동기(psycopg2) 드라이버 URL을 생성합니다."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def CELERY_BROKER_URL(self) -> str:
        """Celery 브로커 URL을 생성합니다."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @computed_field
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        """Celery 결과 백엔드 URL을 생성합니다."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1"

    # --- 설정 로드 순서 지정 ---
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=False
    )

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
        설정 로드 우선순위: Pydantic 기본값 -> config.yml -> .env -> 환경 변수 -> 명시적 초기화 인자
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
