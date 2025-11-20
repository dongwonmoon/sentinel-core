# -*- coding: utf-8 -*-
"""
애플리케이션의 모든 설정을 중앙에서 관리하는 모듈입니다.

이 파일의 주요 역할:
1.  **설정 소스 정의**: `config.yml`, 환경 변수, `.env` 파일 등 다양한 소스에서 설정을 읽어옵니다.
2.  **계층적 설정 모델링**: Pydantic 모델을 사용하여 `app`, `llm`, `db` 등 관련된 설정들을 구조화합니다.
3.  **타입 안정성 보장**: Pydantic을 통해 설정 값의 타입을 검증하고, 잘못된 설정으로 인한 런타임 오류를 방지합니다.
4.  **동적 설정 값 계산**: 데이터베이스 URL과 같이 다른 설정 값들을 조합하여 동적으로 필요한 값을 생성합니다.
5.  **설정 캐싱**: `@lru_cache`를 사용하여 설정 객체를 한 번만 로드하고 재사용하여 성능을 최적화합니다.
"""
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Literal, Optional, Tuple, Type

import yaml
from pydantic import BaseModel, Field, computed_field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

# 로거 설정
# get_settings()가 호출되기 전에 로거가 필요할 수 있으므로, 기본 로거를 여기서 설정합니다.
logger = logging.getLogger(__name__)


@lru_cache
def get_settings() -> "Settings":
    """
    애플리케이션 전체에서 사용될 설정 객체를 반환합니다.

    `@lru_cache(maxsize=1)`와 동일하게 동작하여, 최초 호출 시 설정 객체를 생성하고
    이후의 모든 호출에서는 캐시된 동일한 객체를 반환하여 일관성과 성능을 보장합니다.

    Returns:
        Settings: 애플리케이션의 모든 설정이 포함된 Pydantic 모델 객체
    """
    logger.info("설정 객체를 초기화합니다...")
    settings = Settings()

    # 데이터베이스 URL과 같은 주요 설정 값의 일부를 마스킹하여 로그에 출력
    # 실제 운영 환경에서는 더 정교한 마스킹 처리가 필요할 수 있습니다.
    logger.debug(
        f"로드된 데이터베이스 호스트: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}"
    )
    logger.debug(f"로드된 LLM 모델: {settings.llm.model_name}")
    return settings


# --- 1. YAML 로더 함수 ---
def yaml_config_settings_source() -> dict[str, Any]:
    """
    프로젝트 루트의 'config.yml' 파일을 읽어 Pydantic 설정 소스로 사용합니다.

    이 함수는 Pydantic의 `settings_customise_sources` 메서드 내에서 호출되어,
    YAML 파일의 내용을 파싱하여 파이썬 딕셔너리로 반환합니다.

    Returns:
        dict[str, Any]: YAML 파일의 내용. 파일이 없으면 빈 딕셔너리를 반환합니다.
    """
    config_path = Path(__file__).parent.parent.parent / "config.yml"
    logger.debug(f"'config.yml' 파일 경로: {config_path}")
    if not config_path.exists():
        logger.warning(
            f"'config.yml' 파일을 찾을 수 없습니다. 기본값과 환경 변수만 사용합니다."
        )
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_content = yaml.safe_load(f)
            if yaml_content:
                logger.info(f"'config.yml' 파일에서 설정을 성공적으로 로드했습니다.")
                return yaml_content
            else:
                logger.warning(f"'config.yml' 파일이 비어 있습니다.")
                return {}
    except Exception as e:
        logger.error(f"'config.yml' 파일 로드 중 오류 발생: {e}", exc_info=True)
        return {}


# --- 2. 계층적 설정을 위한 중첩 Pydantic 모델 ---
# 각 클래스는 애플리케이션의 특정 기능 영역에 대한 설정을 그룹화합니다.


class AppSettings(BaseModel):
    """애플리케이션 기본 정보 및 로깅 설정"""

    title: str = Field("Sentinel RAG System", description="애플리케이션의 공식 명칭")
    description: str = Field(
        "Enterprise-grade RAG system with advanced capabilities.",
        description="애플리케이션에 대한 간략한 설명",
    )
    log_level: str = Field(
        "INFO", description="로그 레벨 (DEBUG, INFO, WARNING, ERROR)"
    )
    log_format: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        description="로그 출력 형식",
    )


class LLMSettings(BaseModel):
    """개별 LLM(Large Language Model) 인스턴스에 대한 설정"""

    provider: Literal["ollama", "openai", "anthropic"] = Field(
        ..., description="LLM 제공자 (예: 'ollama', 'openai')"
    )
    model_name: str = Field(..., description="사용할 LLM의 모델명 (예: 'gemma2:9b')")
    api_base: Optional[str] = Field(
        None,
        description="LLM API의 기본 URL (Ollama 또는 자체 호스팅 모델에 필요)",
    )
    temperature: float = Field(
        0.0, description="모델의 창의성 조절 (0.0: 결정적, 1.0: 창의적)"
    )


class EmbeddingSettings(BaseModel):
    """텍스트 임베딩 모델에 대한 설정"""

    provider: Literal["ollama", "openai", "huggingface"] = Field(
        ..., description="임베딩 모델 제공자"
    )
    model_name: str = Field(
        ..., description="사용할 임베딩 모델명 (예: 'nomic-embed-text')"
    )
    api_base: Optional[str] = Field(
        None, description="임베딩 API의 기본 URL (Ollama 등)"
    )


class VectorStoreSettings(BaseModel):
    """벡터 데이터베이스(저장소)에 대한 설정"""

    provider: Literal["pg_vector", "milvus"] = Field(
        ..., description="사용할 벡터 저장소 종류"
    )
    milvus_host: Optional[str] = Field(None, description="Milvus 사용 시 호스트 주소")
    milvus_port: Optional[int] = Field(None, description="Milvus 사용 시 포트 번호")


class RerankerSettings(BaseModel):
    """검색 결과 재순위화(Reranker) 모델에 대한 설정"""

    provider: Literal["none", "cohere", "cross_encoder"] = Field(
        ..., description="사용할 리랭커 종류 ('none'으로 비활성화)"
    )
    model_name: Optional[str] = Field(None, description="Cross Encoder 사용 시 모델명")


# --- 3. 메인 Settings 클래스 ---


class Settings(BaseSettings):
    """
    애플리케이션의 모든 설정을 통합 관리하는 Pydantic BaseSettings 클래스입니다.
    YAML, .env 파일, 환경 변수, 기본값 순서로 설정을 계층적으로 로드합니다.
    """

    # --- .env 또는 환경 변수로만 관리되어야 하는 민감 정보 ---
    # 이 섹션의 설정들은 보안에 민감하므로, 코드나 config.yml에 직접 하드코딩하지 않고
    # .env 파일이나 환경 변수를 통해 주입하는 것을 원칙으로 합니다.

    # 데이터베이스 연결 정보
    POSTGRES_USER: str = Field(..., description="PostgreSQL 사용자 이름")
    POSTGRES_PASSWORD: str = Field(..., description="PostgreSQL 비밀번호")
    POSTGRES_DB: str = Field(..., description="PostgreSQL 데이터베이스 이름")
    POSTGRES_HOST: str = Field("localhost", description="PostgreSQL 호스트 주소")
    POSTGRES_PORT: int = Field(5432, description="PostgreSQL 포트 번호")

    # Redis 연결 정보 (Celery 브로커 및 결과 백엔드용)
    REDIS_HOST: str = Field("localhost", description="Redis 호스트 주소")
    REDIS_PORT: int = Field(6379, description="Redis 포트 번호")

    # JWT 인증 관련 비밀 키 및 설정
    AUTH_SECRET_KEY: str = Field(
        ...,
        description="JWT 서명에 사용될 비밀 키. 외부에 노출되어서는 안 됩니다.",
    )
    AUTH_ALGORITHM: str = Field("HS256", description="JWT 서명 알고리즘")
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        60 * 24 * 7, description="액세스 토큰 만료 시간(분). 예: 7일"
    )

    # 외부 서비스 API 키 (선택 사항)
    # 필요한 서비스의 API 키만 .env 파일에 추가하여 사용합니다.
    OPENAI_API_KEY: Optional[str] = Field(None, description="OpenAI API 키")
    ANTHROPIC_API_KEY: Optional[str] = Field(None, description="Anthropic API 키")
    COHERE_API_KEY: Optional[str] = Field(
        None, description="Cohere API 키 (Reranker용)"
    )
    GOOGLE_API_KEY: Optional[str] = Field(None, description="Google API 키 (검색용)")
    GOOGLE_CSE_ID: Optional[str] = Field(
        None, description="Google Custom Search Engine ID"
    )

    # RunPod 등 외부에서 호스팅되는 Powerful LLM을 위한 별도 API 키
    POWERFUL_OLLAMA_API_KEY: Optional[str] = Field(
        None, description="외부 호스팅 LLM(예: RunPod) 전용 API 키"
    )

    # Ollama API 기본 URL (docker-compose 등에서 주입)
    OLLAMA_BASE_URL: Optional[str] = Field(None, description="Ollama 서비스의 기본 URL")

    # --- config.yml 또는 기본값으로 관리되는 구조화된 설정 ---
    app: AppSettings = Field(default_factory=AppSettings, description="앱 일반 설정")
    llm: LLMSettings = Field(..., description="메인 LLM 설정")
    embedding: EmbeddingSettings = Field(..., description="임베딩 모델 설정")
    vector_store: VectorStoreSettings = Field(..., description="벡터 저장소 설정")
    reranker: RerankerSettings = Field(..., description="리랭커 설정")
    tools_enabled: List[
        Literal["duckduckgo_search", "google_search", "code_execution"]
    ] = Field([], description="활성화할 기본 제공 도구 목록")

    # --- 동적으로 계산되는 필드 (Computed Fields) ---
    # 이 필드들은 다른 설정 값에 의존하여 동적으로 생성됩니다.
    @computed_field(return_type=str)
    @property
    def DATABASE_URL(self) -> str:
        """SQLAlchemy 비동기(asyncpg) 드라이버용 데이터베이스 URL을 생성합니다."""
        url = f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        logger.debug(
            f"비동기 데이터베이스 URL 생성: postgresql+asyncpg://...@{self.POSTGRES_HOST}:***/..."
        )
        return url

    @computed_field(return_type=str)
    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Alembic 마이그레이션을 위한 동기(psycopg2) 드라이버용 데이터베이스 URL을 생성합니다."""
        url = f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        logger.debug(
            f"동기 데이터베이스 URL 생성: postgresql://...@{self.POSTGRES_HOST}:***/..."
        )
        return url

    @computed_field(return_type=str)
    @property
    def CELERY_BROKER_URL(self) -> str:
        """Celery 메시지 브로커(Redis) URL을 생성합니다."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @computed_field(return_type=str)
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        """Celery 작업 결과 백엔드(Redis) URL을 생성합니다."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/1"

    # --- 설정 로드 순서 및 소스 지정 ---
    model_config = SettingsConfigDict(
        env_file=".env",  # .env 파일 경로
        env_file_encoding="utf-8",
        env_nested_delimiter="__",  # 예: LLM__FAST__MODEL_NAME 환경 변수로 llm.fast.model_name 설정
        extra="ignore",  # 모델에 정의되지 않은 추가 필드는 무시
        case_sensitive=False,  # 환경 변수 이름의 대소문자 구분 안 함
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
        설정 로드 우선순위를 커스터마이징합니다.
        Pydantic은 이 메서드가 반환하는 튜플의 순서대로 설정을 덮어씁니다.
        (튜플의 앞 순서가 가장 높은 우선순위를 가집니다.)

        **로드 우선순위 (높은 순 -> 낮은 순):**
        1.  `init_settings`: 코드에서 `Settings()`를 호출할 때 직접 전달된 인자.
        2.  `env_settings`: 시스템 환경 변수.
        3.  `dotenv_settings`: `.env` 파일에 정의된 변수.
        4.  `yaml_config_settings_source`: `config.yml` 파일.
        5.  `file_secret_settings`: Docker 시크릿과 같은 파일 기반 시크릿.
        6.  **Pydantic 모델의 기본값**: 위의 어떤 소스에서도 설정되지 않은 경우 마지막으로 적용됩니다.
        """
        logger.debug("설정 소스 우선순위를 커스터마이징합니다.")
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            yaml_config_settings_source,
            file_secret_settings,
        )
