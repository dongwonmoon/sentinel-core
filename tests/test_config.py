# tests/test_config.py
import os
from unittest.mock import patch
import pytest
import yaml
from pydantic import ValidationError

# 테스트 대상 임포트는 함수 내부 또는 fixture에서 수행하여
# 전역 `settings` 객체가 테스트에 영향을 주지 않도록 합니다.



def test_settings_from_yaml(monkeypatch):
    """
    YAML 파일로부터 설정이 올바르게 로드되는지 테스트합니다.
    """
    def mock_yaml_source():
        return {
            "LLM_TYPE": "ollama",
            "VECTOR_STORE_TYPE": "pg_vector",
            "LOG_LEVEL": "DEBUG",
        }

    # yaml_config_settings_source 함수를 모의(mock)하여 파일 I/O를 피합니다.
    monkeypatch.setattr("src.config.yaml_config_settings_source", mock_yaml_source)

    from src.config import Settings
    settings = Settings()

    assert settings.LLM_TYPE == "ollama"
    assert settings.VECTOR_STORE_TYPE == "pg_vector"
    assert settings.LOG_LEVEL == "DEBUG"
    # YAML 파일에 정의되지 않은 값은 클래스의 기본값을 따라야 합니다.
    assert settings.APP_TITLE == "Sentinel RAG System"

def test_settings_env_overrides_yaml(monkeypatch):
    """
    환경 변수가 YAML 파일의 설정을 덮어쓰는지 (더 높은 우선순위를 갖는지) 테스트합니다.
    """
    def mock_yaml_source():
        return {
            "LLM_TYPE": "ollama",  # 이 값은 환경 변수에 의해 덮어쓰여야 합니다.
            "VECTOR_STORE_TYPE": "pg_vector",
            "APP_TITLE": "YAML Title",  # 이 값도 덮어쓰여야 합니다.
        }

    # yaml_config_settings_source 함수를 모의(mock)하여 파일 I/O를 피합니다.
    monkeypatch.setattr("src.config.yaml_config_settings_source", mock_yaml_source)

    # 환경 변수 설정 (LLM_TYPE을 덮어씀)
    monkeypatch.setenv("LLM_TYPE", "openai")
    monkeypatch.setenv("APP_TITLE", "Test Sentinel")

    from src.config import Settings
    settings = Settings()

    # 환경 변수에서 로드된 값
    assert settings.LLM_TYPE == "openai"
    assert settings.APP_TITLE == "Test Sentinel"
    # YAML에서 로드된 값
    assert settings.VECTOR_STORE_TYPE == "pg_vector"
    # 기본값
    assert settings.OLLAMA_BASE_URL == "http://localhost:11434"

def test_settings_no_yaml_file(monkeypatch):
    """
    config.yml 파일이 없을 때 기본값으로 올바르게 폴백되는지 테스트합니다.
    """
    # config.yml 파일이 존재하지 않는 것처럼 시뮬레이션
    monkeypatch.setattr("src.config.Path.exists", lambda self: False)

    from src.config import Settings
    settings = Settings()

    assert settings.LLM_TYPE == "ollama"
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:password@localhost:5432/sentinel"

def test_settings_validation_error(monkeypatch):
    """
    잘못된 값이 설정되었을 때 Pydantic의 ValidationError가 발생하는지 테스트합니다.
    """
    def mock_yaml_source():
        return {"LLM_TYPE": "ollama"}

    # yaml_config_settings_source 함수를 모의(mock)하여 파일 I/O를 피합니다.
    monkeypatch.setattr("src.config.yaml_config_settings_source", mock_yaml_source)

    # 환경 변수로 잘못된 값을 설정
    monkeypatch.setenv("LLM_TYPE", "invalid_llm_type")

    from src.config import Settings
    with pytest.raises(ValidationError):
        Settings()
