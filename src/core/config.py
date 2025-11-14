from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple, Type
import yaml
from pydantic import BaseModel, Field, computed_field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)
from functools import lru_cache


@lru_cache()
def get_settings():
    return Settings()


# --- 1. YAML 로더 함수 ---
def yaml_config_settings_source() -> dict[str, Any]:
    """
    프로젝트 루트의 'config.yml' 파일을 읽어 Pydantic 설정 소스로 사용합니다.
    """
    # config.py의 위치가 src/core/로 변경되었으므로 경로 수정
    config_path = Path(__file__).parent.parent.parent / "config.yml"
    if not config_path.exists():
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# --- 2. 계층적 설정을 위한 중첩 Pydantic 모델 ---


class AppSettings(BaseModel):
    """애플리케이션 기본 정보"""

    title: str = "Sentinel RAG System"
    description: str = "Enterprise-grade RAG system with advanced capabilities."
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s"


class LLMSettings(BaseModel):
    """개별 LLM 인스턴스에 대한 설정"""

    provider: Literal["ollama", "openai", "anthropic"]
    model_name: str
    api_base: Optional[str] = None
    temperature: float = 0.0


class LLMGroup(BaseModel):
    """LLM 그룹 (fast, powerful)"""

    fast: LLMSettings
    powerful: LLMSettings


class EmbeddingSettings(BaseModel):
    """임베딩 모델 설정"""

    provider: Literal["ollama", "openai", "huggingface"]
    model_name: str
    api_base: Optional[str] = None


class VectorStoreSettings(BaseModel):
    """벡터 저장소 설정"""

    provider: Literal["pg_vector", "milvus"]
    milvus_host: Optional[str] = None
    milvus_port: Optional[int] = None


class RerankerSettings(BaseModel):
    """리랭커 설정"""

    provider: Literal["none", "cohere", "cross_encoder"]
    model_name: Optional[str] = None


# --- 3. 메인 Settings 클래스 ---


class Settings(BaseSettings):
    """
    애플리케이션의 모든 설정을 관리하는 Pydantic BaseSettings 클래스입니다.
    YAML, 환경 변수(.env), 기본값 순서로 설정을 로드합니다.
    """

    # --- .env 또는 환경 변수로만 관리되어야 하는 민감 정보 ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    AUTH_SECRET_KEY: str
    AUTH_ALGORITHM: str = "HS256"
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # API 키 (선택 사항)
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # RunPod 등 Powerful LLM을 위한 별도 API 키
    POWERFUL_OLLAMA_API_KEY: Optional[str] = None

    OLLAMA_BASE_URL: Optional[str] = None

    # --- config.yml 또는 기본값으로 관리되는 구조화된 설정 ---
    app: AppSettings = Field(default_factory=AppSettings)
    llm: LLMGroup
    embedding: EmbeddingSettings
    vector_store: VectorStoreSettings
    reranker: RerankerSettings
    tools_enabled: List[Literal["duckduckgo_search", "google_search", "code_execution"]]

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

    # --- 설정 로드 순서 및 소스 지정 ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",  # llm__fast__model_name 같은 환경변수 지원
        extra="ignore",
        case_sensitive=False,
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
        설정 로드 우선순위:
        1. 명시적 초기화 인자 (init_settings)
        2. 환경 변수 (env_settings)
        3. .env 파일 (dotenv_settings)
        4. config.yml 파일 (yaml_config_settings_source)
        5. Pydantic 모델 기본값
        6. 파일 시크릿 (file_secret_settings)
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_config_settings_source,
            file_secret_settings,
        )
